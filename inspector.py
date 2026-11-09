#!/usr/bin/env python3
import codecs
import json
import os
import queue
import re
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from codex_metadata import read_thread_labels
from codex_records import codex_home, codex_source, list_codex
from codex_trace import list_traces, trace_source
from explanations import explain, explain_sashes, explain_table
from imports import list_import
from records import Record, Source
from token_counts import tokenizer
from trace_view import TraceView

COLUMNS = (
    ("time", "Time", 185),
    ("direction", "Direction", 85),
    ("kind", "Type", 190),
    ("focus_points", "Focus points", 100),
    ("user_texts", "User texts", 90),
    ("replies", "Assistant replies", 125),
    ("summary", "Summary", 300),
    ("tokens", "Raw text tokens", 110),
    ("usage", "Reported tokens", 115),
    ("cached", "Cached input %", 115),
)
TOKEN_COLORS = ("#dcecff", "#fce1ef", "#e5f2d5", "#eee4fb", "#ffebd0")
NUMERIC_COLUMNS = {"focus_points", "user_texts", "replies", "tokens", "usage", "cached"}


@dataclass(frozen=True, slots=True)
class RecordStats:
    encoding: object | None
    tokens: int | None
    usage: int | None
    cached: float | None
    focus_points: int
    user_texts: int
    replies: int


def record_stats(record):
    try:
        document = json.loads(record.raw.removeprefix("\ufeff"))
    except (ValueError, RecursionError):
        document = None
    focus_points, user_texts, replies = count_focus_points(record.raw, document)
    data = document if isinstance(document, dict) else {}
    payload = data.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    model = data.get("model") or payload.get("model")
    usage = data.get("token_usage") or data.get("usage")
    reported = None
    cached_share = None
    if isinstance(usage, dict):
        incoming = usage.get("input_tokens", usage.get("prompt_tokens"))
        details = usage.get("input_tokens_details", usage.get("prompt_tokens_details"))
        cached = usage.get("cached_input_tokens")
        if cached is None and isinstance(details, dict):
            cached = details.get("cached_tokens")
        if (
            type(incoming) is int
            and incoming > 0
            and type(cached) is int
            and 0 <= cached <= incoming
        ):
            cached_share = 100 * cached / incoming
        reported = usage.get("total_tokens")
        if type(reported) is not int:
            incoming, outgoing = usage.get("input_tokens"), usage.get("output_tokens")
            reported = (
                incoming + outgoing
                if type(incoming) is int and type(outgoing) is int
                else None
            )
    try:
        encoding = tokenizer(model if isinstance(model, str) else "")
        count = len(encoding.encode_ordinary(record.raw))
    except (ImportError, OSError, ValueError, RuntimeError):
        encoding, count = None, None
    return RecordStats(
        encoding, count, reported, cached_share, focus_points, user_texts, replies
    )


JSON_STRING = re.compile(r'"(?:[^"\\\x00-\x1f]++|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*+"')
OBJECT_VALUE = re.compile(r"\s*:\s*\{")


def expand_json_objects(value, expanded_keys=None, *, field=False):
    """Expand objects in freshly parsed JSON in place and report whether anything changed."""
    changed = False
    if isinstance(value, str) and value.lstrip().startswith("{"):
        try:
            decoded = json.loads(value)
        except (ValueError, RecursionError):
            pass
        else:
            if isinstance(decoded, dict):
                value = decoded
                changed = True
    if isinstance(value, dict):
        if field and expanded_keys is not None:
            expanded_keys.append(changed)
        for key, child in value.items():
            value[key], child_changed = expand_json_objects(
                child, expanded_keys, field=True
            )
            changed |= child_changed
    elif isinstance(value, list):
        for index, child in enumerate(value):
            value[index], child_changed = expand_json_objects(child, expanded_keys)
            changed |= child_changed
    return value, changed


def pretty_json(document):
    rendered = json.dumps(document, ensure_ascii=False, indent=2)
    return rendered.encode("utf-8", errors="backslashreplace").decode("utf-8")


def collect_focus_text(value, texts):
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped and not stripped.startswith(
            (
                "<environment_context>",
                "# AGENTS.md instructions",
                "<external_codex_apps_",
            )
        ):
            texts.add(value)
    elif isinstance(value, list):
        for item in value:
            collect_focus_text(item, texts)
    elif isinstance(value, dict):
        if value.get("type") == "refusal":
            collect_focus_text(value.get("refusal"), texts)
        for key in ("text", "content", "parts"):
            collect_focus_text(value.get(key), texts)


def focus_highlights(document):
    user_texts, replies = set(), set()
    pending = [document]
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
            continue
        if not isinstance(value, dict):
            continue
        metadata = value.get("metadata")
        if isinstance(metadata, dict) and metadata.get(
            "is_visually_hidden_from_conversation"
        ):
            continue
        pending.extend(value.values())
        author = value.get("author")
        role = value.get("role") or (
            author.get("role") if isinstance(author, dict) else None
        )
        if role == "user":
            collect_focus_text(value.get("content"), user_texts)
        elif role == "assistant" and (
            value.get("phase") in (None, "final_answer")
            and value.get("channel") in (None, "final")
            and value.get("recipient") in (None, "all")
        ):
            collect_focus_text(value.get("content"), replies)
        if isinstance(value.get("model"), str) and isinstance(value.get("input"), str):
            collect_focus_text(value["input"], user_texts)
        if value.get("type") == "user_message":
            collect_focus_text(value.get("message"), user_texts)
    return {
        tag: texts
        for tag, texts in (("user_text", user_texts), ("reply_text", replies))
        if texts
    }


def focus_tags(match, highlights):
    if not highlights:
        return ()
    text = json.loads(match[0])
    return tuple(tag for tag, texts in highlights.items() if text in texts)


def count_focus_points(value, document):
    total = user_texts = replies = 0
    try:
        highlights = focus_highlights(document)
    except RecursionError:
        return 0, 0, 0
    if highlights:
        for match in JSON_STRING.finditer(value):
            tags = focus_tags(match, highlights)
            total += bool(tags)
            user_texts += "user_text" in tags
            replies += "reply_text" in tags
    return total, user_texts, replies


class Inspector:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.home = codex_home()
        self.trace_root = Path(
            os.environ.get("CODEX_ROLLOUT_TRACE_ROOT")
            or (Path.home() / ".codex" / "communication-inspector-traces")
        ).expanduser()
        self.local_sources: list[Source] = []
        self.imported_sources: list[Source] = []
        self.visible_sources: list[Source] = []
        self.records: list[Record] = []
        self.record_stats: list[RecordStats] = []
        self.show_tokens = False
        self.active_record_id = ""
        self.detail_record_key = None
        self.current_source: Source | None = None
        self.pending = queue.SimpleQueue()
        self.request = 0
        self.refreshing = False
        self.importing = False

        self.source_query = tk.StringVar()
        self.record_query = tk.StringVar()
        self.only_focus_points = tk.BooleanVar(value=False)
        self.filters = {}
        self.sort_column = None
        self.sort_reverse = False
        self.coverage = tk.StringVar(value="Select a source to inspect its records.")
        self.status = tk.StringVar()
        self.pretty = tk.BooleanVar(value=True)
        self.drilldown = tk.BooleanVar(value=False)
        self.drilldown_help = "inspector.drilldown.no_record"
        self.wrap = tk.BooleanVar(value=True)

        self.build_ui()
        self.root.after(50, self.poll)
        self.refresh()

    def build_ui(self):
        self.root.title("Communication Inspector")
        self.root.geometry("1250x800")
        self.root.minsize(770, 520)

        header = ttk.Frame(self.root, padding=(12, 9))
        header.pack(fill="x")
        ttk.Label(
            header, text="Communication Inspector", font=("Segoe UI", 16, "bold")
        ).pack(side="left")
        choose_home = ttk.Button(
            header, text="Choose Codex home…", command=self.choose_home
        )
        explain(choose_home, "inspector.choose_home").pack(side="right")
        self.refresh_button = ttk.Button(
            header, text="Refresh Codex", command=self.refresh
        )
        explain(self.refresh_button, "inspector.refresh").pack(side="right", padx=6)
        self.import_button = ttk.Button(
            header, text="Open capture or export…", command=self.open_files
        )
        explain(self.import_button, "inspector.open_files").pack(side="right")

        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        explain_sashes(panes)
        sources = ttk.Frame(panes, padding=(0, 0, 8, 0), width=360)
        details = ttk.Frame(panes, padding=(8, 0, 0, 0))
        panes.add(sources, weight=1)
        panes.add(details, weight=4)

        explain(ttk.Label(sources, text="Sources"), "inspector.sources").pack(
            anchor="w"
        )
        source_filter = ttk.Entry(sources, textvariable=self.source_query)
        explain(source_filter, "inspector.source_filter").pack(fill="x", pady=4)
        self.source_query.trace_add("write", lambda *_: self.show_sources())
        self.sources = tk.Listbox(
            sources, width=36, exportselection=False, activestyle="none"
        )
        explain(self.sources, "inspector.sources")
        self.scrollable(sources, self.sources)
        self.sources.bind("<<ListboxSelect>>", self.choose_source)

        scope_bar = ttk.Frame(details)
        scope_bar.pack(fill="x", pady=(0, 8))
        self.trace_button = ttk.Button(
            scope_bar, text="Analyze trace…", command=self.analyze_trace
        )
        explain(self.trace_button, "inspector.analyze_trace").pack(
            side="right", anchor="n", padx=(6, 0)
        )
        self.trace_button.state(["disabled"])
        scope = ttk.Label(
            scope_bar, textvariable=self.coverage, justify="left", wraplength=620
        )
        explain(scope, "inspector.coverage").pack(side="left", fill="x", expand=True)
        scope.bind(
            "<Configure>",
            lambda event: scope.configure(wraplength=max(event.width - 10, 120)),
        )

        filters = ttk.Frame(details)
        filters.pack(fill="x", pady=(0, 6))
        explain(
            ttk.Label(filters, text="Find in records"), "inspector.record_query"
        ).pack(side="left")
        query = ttk.Entry(filters, textvariable=self.record_query, width=10)
        explain(query, "inspector.record_query").pack(
            side="left", fill="x", expand=True, padx=6
        )
        query.bind("<Return>", lambda _: self.show_records())
        find = ttk.Button(filters, text="Find", command=self.show_records)
        explain(find, "inspector.find").pack(side="left")
        clear = ttk.Button(filters, text="Clear", command=self.clear_filters)
        explain(clear, "inspector.clear").pack(side="left", padx=6)
        focus_filter = ttk.Checkbutton(
            filters,
            text="Has focus points",
            variable=self.only_focus_points,
            command=self.show_records,
        )
        explain(focus_filter, "inspector.filter.focus_points").pack(
            side="right", padx=3
        )
        for field, label in (("kind", "Type"), ("direction", "Direction")):
            button = ttk.Button(
                filters,
                text=f"{label} filter…",
                command=lambda f=field, l=label: self.choose_filter(f, l),
            )
            explain(button, f"inspector.filter.{field}").pack(side="right", padx=3)

        split = ttk.Panedwindow(details, orient="vertical")
        split.pack(fill="both", expand=True)
        explain_sashes(split)
        events = ttk.Frame(split)
        raw = ttk.Frame(split)
        split.add(events, weight=2)
        split.add(raw, weight=3)

        columns = tuple(field for field, _, _ in COLUMNS)
        self.events = ttk.Treeview(
            events, columns=columns, show="headings", height=9, selectmode="extended"
        )
        for column, label, width in COLUMNS:
            self.events.heading(
                column, text=label, command=lambda c=column: self.sort_by(c)
            )
            self.events.column(
                column, width=width, minwidth=65, stretch=column == "summary"
            )
        self.scrollable(events, self.events)
        self.events.bind("<Button-1>", self.remember_clicked_record)
        self.events.bind("<<TreeviewSelect>>", lambda _: self.show_detail())
        self.events.bind("<Control-c>", self.copy_selected_records)
        explain_table(
            self.events,
            {column: f"inspector.column.{column}" for column in columns},
            body="inspector.records",
        )

        actions = ttk.Frame(raw)
        actions.pack(fill="x", pady=(5, 4))
        explain(ttk.Label(actions, text="Record payload"), "inspector.payload").pack(
            side="left"
        )
        pretty = ttk.Checkbutton(
            actions, text="Pretty JSON", variable=self.pretty, command=self.show_detail
        )
        explain(pretty, "inspector.pretty").pack(side="left", padx=8)
        self.drilldown_button = ttk.Checkbutton(
            actions,
            text="Drilldown",
            variable=self.drilldown,
            command=self.show_detail,
            state="disabled",
        )
        explain(self.drilldown_button, lambda: self.drilldown_help).pack(
            side="left", padx=4
        )
        wrap = ttk.Checkbutton(
            actions, text="Wrap", variable=self.wrap, command=self.set_wrap
        )
        explain(wrap, "inspector.wrap").pack(side="left")
        copy_payload = ttk.Button(
            actions, text="Copy payload", command=self.copy_record
        )
        explain(copy_payload, "inspector.copy_payload").pack(side="right")

        self.token_button = ttk.Button(
            actions, text="Show tokenization", command=self.toggle_tokens
        )
        explain(self.token_button, "inspector.tokenization").pack(side="right", padx=4)
        self.token_status = ttk.Label(raw)
        explain(self.token_status, "inspector.token_status").pack(fill="x")
        self.focus_index = 0
        style = ttk.Style(self.root)
        style.configure("Focus.TButton", font=("Segoe UI", 11, "bold"))
        style.map("Focus.TButton", foreground=[("disabled", "#999999")])
        self.focus_button = ttk.Button(
            actions,
            text="↓",
            width=4,
            state="disabled",
            style="Focus.TButton",
            command=self.focus_text,
        )
        explain(
            self.focus_button,
            lambda: (
                "inspector.focus_text.disabled"
                if self.focus_button.instate(("disabled",))
                else "inspector.focus_text"
            ),
        ).pack(side="left", padx=4)

        self.detail = tk.Text(
            raw, wrap="word", font=("Consolas", 10), state="disabled", undo=False
        )
        self.detail.tag_configure("user_text", foreground="#b00020")
        self.detail.tag_configure("reply_text", foreground="#006629")
        self.detail.tag_configure("expanded_key", foreground="#6740a4")
        self.detail.tag_configure("focus_target")
        for index, color in enumerate(TOKEN_COLORS):
            self.detail.tag_configure(f"token_{index}", background=color)
        self.detail.tag_configure("focused_text", background="#ffe58a")
        explain(self.detail, "inspector.payload")
        self.scrollable(raw, self.detail)
        status = ttk.Label(self.root, textvariable=self.status, padding=(12, 0, 12, 8))
        explain(status, "inspector.status").pack(fill="x")

    @staticmethod
    def scrollable(frame, widget):
        bar_y = ttk.Scrollbar(frame, orient="vertical", command=widget.yview)
        bar_x = ttk.Scrollbar(frame, orient="horizontal", command=widget.xview)
        widget.configure(yscrollcommand=bar_y.set, xscrollcommand=bar_x.set)
        bar_y.pack(side="right", fill="y")
        bar_x.pack(side="bottom", fill="x")
        widget.pack(fill="both", expand=True)

    def work(self, action, token, load):
        def run():
            try:
                self.pending.put((action, token, load(), None))
            except Exception as error:
                self.pending.put((action, token, None, str(error)))

        threading.Thread(target=run, daemon=True).start()

    def choose_home(self):
        path = filedialog.askdirectory(title="Choose Codex home", initialdir=self.home)
        if path and not self.refreshing:
            self.home = Path(path)
            self.refresh()

    def refresh(self):
        if self.refreshing:
            return
        self.refreshing = True
        self.refresh_button.state(["disabled"])
        self.status.set(f"Finding Codex sessions under {self.home}…")
        home = self.home

        def read_sources():
            labels = read_thread_labels(home)
            rollouts = list_codex(home, labels)
            return list_traces(self.trace_root, labels) + rollouts

        self.work("refresh", None, read_sources)

    def open_files(self):
        paths = filedialog.askopenfilenames(
            title="Open a ChatGPT export, browser HAR, or local capture",
            filetypes=[
                ("Captures and exports", "*.zip *.har *.json *.jsonl *.zst *.sse"),
                ("All files", "*"),
            ],
        )
        if not paths or self.importing:
            return
        self.importing = True
        self.import_button.state(["disabled"])
        self.status.set(f"Opening {len(paths)} file(s)…")
        home = self.home

        def read_imports():
            sources, errors = [], []
            labels = None
            for filename in paths:
                path = Path(filename)
                try:
                    is_trace = (
                        path.name in ("manifest.json", "trace.jsonl")
                        and (path.parent / "trace.jsonl").is_file()
                    )
                    is_rollout = path.name.lower().endswith((".jsonl", ".jsonl.zst"))
                    if is_trace or is_rollout:
                        if labels is None:
                            labels = read_thread_labels(home)
                        sources.append(
                            trace_source(path, labels)
                            if is_trace
                            else codex_source(path, labels)
                        )
                    else:
                        sources.extend(list_import(path))
                except Exception as error:
                    errors.append(f"{path.name}: {error}")
            return sources, errors

        self.work("import", None, read_imports)

    def poll(self):
        while not self.pending.empty():
            action, token, result, error = self.pending.get_nowait()
            if action == "refresh":
                self.refreshing = False
                self.refresh_button.state(["!disabled"])
                if error:
                    self.status.set(f"Couldn't find Codex sessions. {error}")
                    continue
                previous = self.current_source
                replacement = None
                if previous in self.local_sources:
                    replacement = next(
                        (
                            source
                            for source in result
                            if source.coverage == previous.coverage
                        ),
                        None,
                    )
                    if replacement is None:
                        matches = [
                            source
                            for source in result
                            if source.title == previous.title
                        ]
                        if len(matches) == 1:
                            replacement = matches[0]
                self.local_sources = result
                self.show_sources()
                self.status.set(f"{len(result):,} local Codex sessions and traces")
                if replacement is not None:
                    self.activate(replacement)
            elif action == "import":
                self.importing = False
                self.import_button.state(["!disabled"])
                if error:
                    self.status.set(f"Couldn't import files. {error}")
                    continue
                sources, errors = result
                self.imported_sources[0:0] = sources
                if sources:
                    self.source_query.set("")
                    self.activate(sources[0])
                self.status.set(
                    " | ".join([f"Imported {len(sources):,} source(s)", *errors])
                )
                if errors:
                    messagebox.showwarning(
                        "Import details", "\n\n".join(errors), parent=self.root
                    )
            elif action in ("trace_analysis", "trace_context"):
                if action == "trace_analysis":
                    token.show_analysis(result, error)
                else:
                    view, call_id = token
                    view.show_context(call_id, result, error)
            elif token == self.request:
                if error:
                    self.status.set(f"Couldn't read this source. {error}")
                    continue
                self.records, self.record_stats = result
                self.show_records()
        self.root.after(50, self.poll)

    def show_sources(self):
        query = self.source_query.get().strip().casefold()
        self.visible_sources = [
            source
            for source in [*self.imported_sources, *self.local_sources]
            if query in source.title.casefold()
        ]
        self.sources.delete(0, "end")
        for source in self.visible_sources:
            self.sources.insert("end", source.title)
        self.highlight_source()

    def highlight_source(self):
        self.sources.selection_clear(0, "end")
        if self.current_source in self.visible_sources:
            index = self.visible_sources.index(self.current_source)
            self.sources.selection_set(index)
            self.sources.see(index)

    def choose_source(self, _event):
        selection = self.sources.curselection()
        if selection:
            source = self.visible_sources[selection[0]]
            if source is not self.current_source:
                self.activate(source)

    def activate(self, source):
        self.current_source = source
        self.highlight_source()
        self.request += 1
        self.records = []
        self.record_stats = []
        self.coverage.set(source.coverage)
        self.trace_button.state(["!disabled" if source.trace_path else "disabled"])
        self.active_record_id = ""
        self.show_records()
        self.status.set(f"Reading {source.title}…")

        def read():
            records = list(source.load())
            return records, [record_stats(record) for record in records]

        self.work("records", self.request, read)

    def analyze_trace(self):
        source = self.current_source
        if source and source.trace_path:
            TraceView(self.root, source, self.work)

    def clear_filters(self):
        self.record_query.set("")
        self.only_focus_points.set(False)
        self.filters.clear()
        self.show_records()

    def sort_by(self, column):
        self.sort_reverse = self.sort_column == column and not self.sort_reverse
        self.sort_column = column
        for field, label, _ in COLUMNS:
            arrow = (" ▼" if self.sort_reverse else " ▲") if field == column else ""
            self.events.heading(field, text=label + arrow)
        self.show_records()

    def choose_filter(self, field, label):
        available = {getattr(record, field) for record in self.records}
        values = sorted(available | self.filters.get(field, set()), key=str.casefold)
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Filter by {label}")
        dialog.transient(self.root)
        dialog.grab_set()
        instructions = ttk.Label(dialog, text="Selected values are shown.")
        explain(instructions, "inspector.filter.options").pack(padx=12, pady=8)
        actions = ttk.Frame(dialog, padding=8)
        actions.pack(side="bottom", fill="x")
        options = tk.Listbox(
            dialog, selectmode="multiple", exportselection=False, width=56, height=14
        )
        explain(options, "inspector.filter.options")
        self.scrollable(dialog, options)
        for index, value in enumerate(values):
            options.insert("end", value or "(blank)")
            if field not in self.filters or value in self.filters[field]:
                options.selection_set(index)

        def apply():
            selected = {values[index] for index in options.curselection()}
            if selected == set(values):
                self.filters.pop(field, None)
            else:
                self.filters[field] = selected
            dialog.destroy()
            self.show_records()

        select_all = ttk.Button(
            actions, text="Select all", command=lambda: options.selection_set(0, "end")
        )
        explain(select_all, "inspector.filter.all").pack(side="left")
        select_none = ttk.Button(
            actions,
            text="Select none",
            command=lambda: options.selection_clear(0, "end"),
        )
        explain(select_none, "inspector.filter.none").pack(side="left")
        explain(
            ttk.Button(actions, text="Apply", command=apply), "inspector.filter.apply"
        ).pack(side="right")

    def show_records(self):
        selected = self.events.selection()
        self.events.delete(*self.events.get_children())
        needle = self.record_query.get().strip().casefold()
        only_focus_points = self.only_focus_points.get()
        count = 0
        rows = list(enumerate(self.records))
        if self.sort_column:
            field = {"time": "timestamp"}.get(self.sort_column, self.sort_column)
            if field in NUMERIC_COLUMNS:

                def sort_value(row):
                    value = getattr(self.record_stats[row[0]], field)
                    return value if value is not None else -1

                rows.sort(key=sort_value, reverse=self.sort_reverse)
            else:
                rows.sort(
                    key=lambda row: getattr(row[1], field).casefold(),
                    reverse=self.sort_reverse,
                )
        for index, record in rows:
            stats = self.record_stats[index]
            if only_focus_points and not stats.focus_points:
                continue
            if any(
                getattr(record, field) not in allowed
                for field, allowed in self.filters.items()
            ):
                continue
            if needle and not any(
                needle in part.casefold()
                for part in (record.kind, record.summary, record.raw)
            ):
                continue
            self.events.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    record.timestamp,
                    record.direction,
                    record.kind,
                    stats.focus_points,
                    stats.user_texts,
                    stats.replies,
                    record.summary,
                    stats.tokens if stats.tokens is not None else "—",
                    stats.usage if stats.usage is not None else "—",
                    f"{stats.cached:.1f}%" if stats.cached is not None else "—",
                ),
            )
            count += 1
        retained = [item for item in selected if self.events.exists(item)]
        if retained:
            self.events.selection_set(retained)
            item = (
                self.active_record_id
                if self.active_record_id in retained
                else retained[-1]
            )
            self.events.focus(item)
            self.events.see(item)
        elif count:
            item = self.events.get_children()[0]
            self.events.selection_set(item)
            self.events.focus(item)
        self.show_detail()
        self.status.set(f"{count:,} of {len(self.records):,} records")

    def remember_clicked_record(self, event):
        item = self.events.identify_row(event.y)
        if item and self.events.identify_region(event.x, event.y) in ("cell", "tree"):
            self.active_record_id = item
            self.root.after_idle(self.show_detail)

    def selected_record_id(self):
        selection = self.events.selection()
        if self.active_record_id in selection:
            return self.active_record_id
        focused = self.events.focus()
        return focused if focused in selection else (selection[-1] if selection else "")

    def selected_record(self):
        item = self.selected_record_id()
        return self.records[int(item)] if item else None

    def copy_selected_records(self, _event):
        selected = set(self.events.selection())
        if not selected:
            return

        def markdown_row(values):
            cells = [
                str(value)
                .replace("\\", "\\\\")
                .replace("|", "\\|")
                .replace("\r\n", "<br>")
                .replace("\r", "<br>")
                .replace("\n", "<br>")
                for value in values
            ]
            return "| " + " | ".join(cells) + " |"

        rows = [
            markdown_row(label for _, label, _ in COLUMNS),
            markdown_row(["---"] * len(COLUMNS)),
        ]
        rows.extend(
            markdown_row(self.events.item(item, "values"))
            for item in self.events.get_children()
            if item in selected
        )
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(rows))
        self.status.set(f"Copied {len(selected):,} records as Markdown")
        return "break"

    def show_detail(self):
        item = self.selected_record_id()
        record = self.records[int(item)] if item else None
        record_key = (self.request, item) if item else None
        new_record = record_key != self.detail_record_key
        if new_record:
            self.detail_record_key = record_key
            self.drilldown.set(False)
            self.drilldown_button.state(["disabled"])
            self.drilldown_help = (
                "inspector.drilldown.unreadable"
                if record
                else "inspector.drilldown.no_record"
            )

        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        value = record.raw if record else ""
        highlights = {}
        expanded_keys = None
        original_view = None
        if value:
            try:
                document = json.loads(value.removeprefix("\ufeff"))
                highlights = focus_highlights(document)
                if self.pretty.get():
                    value = pretty_json(document)
                show_expanded = self.drilldown.get()
                if new_record or show_expanded:
                    keys = [] if show_expanded else None
                    document, changed = expand_json_objects(document, keys)
                    if new_record:
                        self.drilldown_help = (
                            "inspector.drilldown"
                            if changed
                            else "inspector.drilldown.no_objects"
                        )
                        if changed:
                            self.drilldown_button.state(["!disabled"])
                    elif changed:
                        rendered = pretty_json(document)
                        original_view = value if self.show_tokens else None
                        value = rendered
                        expanded_keys = iter(keys)
            except ValueError:
                pass
            except RecursionError:
                self.drilldown.set(False)
                self.drilldown_button.state(["disabled"])
                self.drilldown_help = "inspector.drilldown.too_deep"
            finally:
                document = None
        self.detail.insert("1.0", value)
        self.token_status.configure(text="")
        if record and self.show_tokens:
            self.color_tokens(
                value, self.record_stats[int(item)].encoding, original_view
            )
        self.focus_index = 0
        if expanded_keys is not None or highlights:
            for match in JSON_STRING.finditer(value):
                start = f"1.0 + {match.start() + 1} chars"
                end = f"1.0 + {match.end() - 1} chars"
                if expanded_keys is not None and OBJECT_VALUE.match(value, match.end()):
                    if next(expanded_keys, False):
                        self.detail.tag_add("expanded_key", start, end)
                if tags := focus_tags(match, highlights):
                    for tag in tags:
                        self.detail.tag_add(tag, start, end)
                    self.detail.tag_add("focus_target", start, end)
        self.detail.configure(state="disabled")
        self.focus_button.state(
            ["!disabled" if self.detail.tag_ranges("focus_target") else "disabled"]
        )

    def toggle_tokens(self):
        self.show_tokens = not self.show_tokens
        self.token_button.configure(
            text="Hide tokenization" if self.show_tokens else "Show tokenization"
        )
        self.show_detail()

    def color_tokens(self, value, encoding, original_view=None):
        if encoding is None:
            self.token_status.configure(
                text="Tokenizer unavailable. Install tiktoken to enable token colors."
            )
            return
        tokens = encoding.encode_ordinary(value)
        decoder = codecs.getincrementaldecoder("utf-8")()
        ranges = [[] for _ in TOKEN_COLORS]
        start = 0
        for index, token in enumerate(tokens):
            end = start + len(decoder.decode(encoding.decode_single_token_bytes(token)))
            if end > start:
                ranges[index % len(ranges)].extend(
                    (f"1.0 + {start} chars", f"1.0 + {end} chars")
                )
            start = end
        for index, spans in enumerate(ranges):
            if spans:
                self.detail.tag_add(f"token_{index}", *spans)
        count = (
            len(tokens)
            if original_view is None
            else len(encoding.encode_ordinary(original_view))
        )
        label = "displayed-text" if original_view is None else "pre-drilldown text"
        self.token_status.configure(
            text=f"{count:,} {label} tokens · {encoding.name} · local estimate"
        )

    def focus_text(self):
        ranges = self.detail.tag_ranges("focus_target")
        if not ranges:
            return
        start, end = ranges[self.focus_index : self.focus_index + 2]
        self.focus_index = (self.focus_index + 2) % len(ranges)
        self.detail.tag_remove("focused_text", "1.0", "end")
        self.detail.tag_add("focused_text", start, end)
        self.detail.see(start)

    def set_wrap(self):
        self.detail.configure(wrap="word" if self.wrap.get() else "none")

    def copy_record(self):
        record = self.selected_record()
        if record:
            self.root.clipboard_clear()
            self.root.clipboard_append(record.raw)
            self.status.set("Copied the record payload to the clipboard")


if __name__ == "__main__":
    root = tk.Tk()
    Inspector(root)
    root.mainloop()
