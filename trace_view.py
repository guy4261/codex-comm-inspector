"""Trace analysis window for Communication Inspector."""

import tkinter as tk
from collections import defaultdict
from tkinter import ttk

from explanations import explain, explain_sashes, explain_table, explain_tabs
from trace_audit import (
    context_evidence,
    markdown_evidence,
    previous_requests,
    raw_evidence,
    read_analysis,
    request_context,
    tool_evidence,
    usage_evidence,
)

PREVIEW_CHARACTERS = 80_000


def display(value):
    if value is None:
        return "—"
    return f"{value:,}" if isinstance(value, int) else value


class TraceView:
    def __init__(self, root, source, work):
        self.window = tk.Toplevel(root)
        self.window.title("Communication Inspector · Trace analysis")
        self.window.geometry("1140x800")
        self.window.minsize(690, 550)
        self.work = work
        self.calls = []
        self.previous = {}
        self.tools = []
        self.tools_by_call = defaultdict(list)
        self.context_cache = {}
        self.context_pending = set()
        self.active_call = None
        self.evidence = {}
        self.visible_tools = []

        layout = ttk.Frame(self.window, padding=12)
        layout.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="Reading trace…")
        explain(ttk.Label(layout, text=source.title), "trace.source_title").pack(
            anchor="w", pady=(0, 4)
        )
        explain(ttk.Label(layout, textvariable=self.status), "trace.status").pack(
            anchor="w", pady=(0, 8)
        )
        calls_label = ttk.Label(
            layout,
            text="Model calls · reported tokens, with uncached input derived when needed",
        )
        explain(calls_label, "trace.model_calls").pack(anchor="w")
        self.call_table = self.make_table(
            layout,
            (
                ("Request #", 76, "trace.request_event"),
                ("Inference call ID", 250, "trace.call_id"),
                ("Request snapshot", 190, "trace.snapshot"),
                ("Input", 85, "trace.input"),
                ("Cached input", 91, "trace.cached_input"),
                ("Uncached input", 99, "trace.uncached_input"),
                ("Output", 80, "trace.output"),
                ("Reasoning", 85, "trace.reasoning"),
            ),
            body="trace.model_calls",
            height=7,
            expand=False,
        )
        self.call_table.bind("<<TreeviewSelect>>", self.select_call)
        usage_bar = ttk.Frame(layout)
        usage_bar.pack(fill="x", pady=5)
        self.call_details = tk.StringVar()
        self.copy_usage_button = ttk.Button(
            usage_bar, text="Copy usage evidence", command=self.copy_usage
        )
        explain(self.copy_usage_button, "trace.copy_usage").pack(side="right")
        self.copy_usage_button.state(["disabled"])
        explain(
            ttk.Label(usage_bar, textvariable=self.call_details), "trace.call_details"
        ).pack(side="left")

        self.tabs = ttk.Notebook(layout)
        self.tabs.pack(fill="both", expand=True)
        payloads = ttk.Frame(self.tabs, padding=8)
        context = ttk.Frame(self.tabs, padding=8)
        tools = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(payloads, text="Call payloads")
        self.tabs.add(context, text="Context breakdown")
        self.tabs.add(tools, text="Tool results")
        explain_tabs(
            self.tabs,
            {
                payloads: "trace.payloads_tab",
                context: "trace.context_tab",
                tools: "trace.tools_tab",
            },
        )
        self.tools_tab = str(tools)
        self.tabs.bind("<<NotebookTabChanged>>", self.change_tab)
        sizes = ttk.Label(
            payloads, text="Saved payload sizes include formatting and trace fields."
        )
        explain(sizes, "trace.payload_sizes").pack(anchor="w")
        self.payload_table = self.make_table(
            payloads,
            (
                ("Event #", 75, "trace.event"),
                ("Payload type", 160, "trace.payload_type"),
                ("Lifecycle event", 175, "trace.lifecycle"),
                ("Payload reference", 280, "trace.reference"),
                ("Bytes", 90, "trace.bytes"),
                ("Characters", 100, "trace.payload_characters"),
            ),
            body="trace.copyable_rows",
        )
        self.add_copy(payloads, self.payload_table)

        self.context_note = tk.StringVar()
        context_note = ttk.Label(
            context, textvariable=self.context_note, justify="left", wraplength=650
        )
        explain(context_note, "trace.context_note").pack(anchor="w", pady=(0, 4))
        self.context_tab = str(context)
        self.context_table = self.make_table(
            context,
            (
                ("Source", 176, "trace.context_source"),
                ("Characters", 95, "trace.context_characters"),
                ("Tokens", 90, "trace.context_tokens"),
                ("New characters", 116, "trace.new_characters"),
                ("New tokens", 95, "trace.new_tokens"),
                ("Repeated characters", 144, "trace.repeated_characters"),
                ("Repeated tokens", 120, "trace.repeated_tokens"),
            ),
            body="trace.copyable_rows",
        )
        self.add_copy(context, self.context_table)

        self.all_tools = tk.BooleanVar()
        all_tools = ttk.Checkbutton(
            tools,
            text="Show results from all calls",
            variable=self.all_tools,
            command=self.show_tools,
        )
        explain(all_tools, "trace.all_tools").pack(anchor="w")
        tool_split = ttk.Panedwindow(tools, orient="vertical")
        tool_split.pack(fill="both", expand=True)
        explain_sashes(tool_split)
        tool_rows = ttk.Frame(tool_split)
        tool_split.add(tool_rows, weight=1)
        self.tool_table = self.make_table(
            tool_rows,
            (
                ("Event #", 72, "trace.event"),
                ("Tool", 170, "trace.tool"),
                ("Status", 100, "trace.tool_status"),
                ("Diagnostics", 300, "trace.diagnostics"),
                ("Emitted characters", 134, "trace.emitted_characters"),
                ("Excerpt characters", 134, "trace.excerpt_characters"),
            ),
            body="trace.tool_rows",
            height=4,
        )
        self.tool_table.bind("<<TreeviewSelect>>", self.show_tool_detail)
        self.add_copy(tool_rows, self.tool_table)
        excerpts = ttk.Frame(tool_split)
        tool_split.add(excerpts, weight=2)
        self.tool_note = tk.StringVar()
        tool_note = ttk.Label(
            excerpts, textvariable=self.tool_note, wraplength=650, justify="left"
        )
        explain(tool_note, "trace.tool_details").pack(anchor="w", pady=4)
        side_by_side = ttk.Panedwindow(excerpts, orient="horizontal")
        side_by_side.pack(fill="both", expand=True)
        explain_sashes(side_by_side)
        self.emitted = self.make_preview(
            side_by_side, "Emitted result", "trace.emitted_preview"
        )
        self.excerpt = self.make_preview(
            side_by_side, "Excerpt in next matching request", "trace.excerpt_preview"
        )

        work("trace_analysis", self, lambda: read_analysis(source.trace_path))

    @staticmethod
    def make_table(parent, columns, *, body, height=10, expand=True):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=expand, pady=4)
        table = ttk.Treeview(
            frame,
            columns=tuple(label for label, _, _ in columns),
            show="headings",
            height=height,
            selectmode="browse",
        )
        for index, (label, width, _) in enumerate(columns):
            table.heading(label, text=label)
            table.column(label, width=width, minwidth=width, stretch=index == 1)
        explain_table(table, {label: key for label, _, key in columns}, body=body)
        TraceView.scrollable(frame, table)
        return table

    @staticmethod
    def scrollable(frame, widget):
        vertical = ttk.Scrollbar(frame, orient="vertical", command=widget.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=widget.xview)
        widget.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side="right", fill="y")
        horizontal.pack(side="bottom", fill="x")
        widget.pack(fill="both", expand=True)

    @staticmethod
    def make_preview(parent, label, explanation):
        frame = ttk.Frame(parent, padding=(3, 0))
        parent.add(frame, weight=1)
        heading = tk.StringVar(value=label)
        explain(ttk.Label(frame, textvariable=heading), explanation).pack(
            anchor="w", pady=(0, 2)
        )
        text = tk.Text(
            frame,
            height=8,
            width=25,
            wrap="none",
            state="disabled",
            font=("Consolas", 10),
        )
        explain(text, explanation)
        TraceView.scrollable(frame, text)
        return heading, text

    def add_copy(self, parent, table):
        actions = ttk.Frame(parent)
        actions.pack(fill="x")
        button = ttk.Button(
            actions, text="Copy evidence", command=lambda: self.copy_selected(table)
        )
        explain(button, "trace.copy_evidence").pack(side="right")
        table.bind("<Control-c>", lambda _: self.copy_selected(table))
        self.evidence[table] = {}

    def show_analysis(self, result, error):
        if not self.window.winfo_exists():
            return
        if error:
            self.status.set(f"Couldn't analyze trace. {error}")
            return
        analysis, self.tools = result
        self.calls = analysis.calls
        self.previous = previous_requests(self.calls)
        for tool in self.tools:
            self.tools_by_call[tool.inference_call_id].append(tool)
        self.status.set(
            f"{len(self.calls):,} model calls · {len(self.tools):,} tool results · {analysis.trace_id}"
        )
        for index, call in enumerate(self.calls):
            if call.request is None or not isinstance(call.request.document, dict):
                snapshot = "Request unavailable"
            elif call.delta:
                snapshot = "Delta · previous response"
            else:
                snapshot = "Full capture"
            self.call_table.insert(
                "",
                "end",
                iid=str(index),
                values=tuple(
                    map(
                        display,
                        (
                            call.request.sequence if call.request else None,
                            call.call_id,
                            snapshot,
                            call.usage.input_tokens,
                            call.usage.cached_input_tokens,
                            call.usage.uncached_input_tokens,
                            call.usage.output_tokens,
                            call.usage.reasoning_tokens,
                        ),
                    )
                ),
            )
        if self.calls:
            self.call_table.selection_set("0")
            self.call_table.focus("0")

    def select_call(self, _event):
        selection = self.call_table.selection()
        if not selection:
            return
        call = self.calls[int(selection[0])]
        if call is self.active_call:
            return
        self.active_call = call
        details = []
        if call.model:
            details.append(call.model)
        if call.status:
            details.append(call.status.capitalize())
        if call.duplicate_count:
            details.append(
                f"{call.duplicate_count:,} duplicate lifecycle payloads collapsed"
            )
        if call.previous_response_id:
            details.append(f"Previous response {call.previous_response_id}")
        self.call_details.set(" · ".join(details))
        self.copy_usage_button.state(
            ["!disabled" if self.reported_usage() else "disabled"]
        )
        self.show_payloads()
        self.change_tab()

    def change_tab(self, _event=None):
        tab = self.tabs.select()
        if tab == self.context_tab:
            self.load_context()
        elif tab == self.tools_tab:
            self.show_tools()

    def reset_table(self, table):
        table.delete(*table.get_children())
        self.evidence[table].clear()

    def show_payloads(self):
        call = self.active_call
        self.reset_table(self.payload_table)
        payloads = [
            (payload, stage)
            for payload, stage in (
                (call.request, "Request"),
                (call.response, "Response"),
            )
            if payload is not None
        ]
        payloads.extend(
            (payload, "Other recorded variant") for payload in call.other_payloads
        )
        for event in call.tools:
            payloads.extend((payload, event.kind) for payload in event.payloads)
        for payload, stage in sorted(payloads, key=lambda pair: pair[0].sequence):
            item = self.payload_table.insert(
                "",
                "end",
                values=tuple(
                    map(
                        display,
                        (
                            payload.sequence,
                            payload.kind,
                            stage,
                            payload.path,
                            payload.raw_bytes,
                            payload.raw_chars,
                        ),
                    )
                ),
            )
            self.evidence[self.payload_table][item] = [raw_evidence(payload)]

    def load_context(self):
        if self.tabs.select() != self.context_tab:
            return
        call = self.active_call
        self.reset_table(self.context_table)
        if (
            call is None
            or call.request is None
            or not isinstance(call.request.document, dict)
        ):
            self.context_note.set("No readable request snapshot for this call.")
            return
        if call.call_id in self.context_cache:
            result, error = self.context_cache[call.call_id]
            self.render_context(call, result, error)
        else:
            self.context_note.set("Measuring decoded request text…")
            if call.call_id not in self.context_pending:
                self.context_pending.add(call.call_id)
                baseline = self.previous.get(call.call_id)
                self.work(
                    "trace_context",
                    (self, call.call_id),
                    lambda: request_context(call, baseline),
                )

    def show_context(self, call_id, result, error):
        if not self.window.winfo_exists():
            return
        self.context_pending.discard(call_id)
        self.context_cache[call_id] = result, error
        if self.active_call and call_id == self.active_call.call_id:
            self.load_context()

    def render_context(self, call, result, error):
        if error:
            self.context_note.set(f"Couldn't measure this snapshot. {error}")
            return
        encoding, rows = result
        baseline = self.previous.get(call.call_id)
        scope = "Captured delta fields" if call.delta else "Captured full request"
        if baseline:
            prior = " (delta)" if baseline.delta else ""
            scope += f" compared with request #{baseline.request.sequence}{prior} on the same thread"
        else:
            scope += " with no earlier request on this thread"
        method = (
            "Unicode characters"
            if encoding == "Unicode characters"
            else f"Unicode characters and local {encoding} tokens"
        )
        self.context_note.set(
            f"{scope}. Exact decoded segments are matched by occurrence. Counts use {method}."
        )
        for row in rows:
            item = self.context_table.insert(
                "",
                "end",
                values=tuple(
                    map(
                        display,
                        (
                            row.source,
                            row.chars,
                            row.tokens,
                            row.new_chars,
                            row.new_tokens,
                            row.repeated_chars,
                            row.repeated_tokens,
                        ),
                    )
                ),
            )
            self.evidence[self.context_table][item] = [
                context_evidence(call, baseline, encoding, row)
            ]

    def show_tools(self):
        self.reset_table(self.tool_table)
        call_id = self.active_call.call_id if self.active_call else None
        self.visible_tools = (
            self.tools if self.all_tools.get() else self.tools_by_call.get(call_id, [])
        )
        for index, tool in enumerate(self.visible_tools):
            payload = tool.emitted_payload or tool.request_payload
            item = self.tool_table.insert(
                "",
                "end",
                iid=str(index),
                values=tuple(
                    map(
                        display,
                        (
                            payload.sequence if payload else None,
                            tool.tool_name,
                            tool.status,
                            ", ".join(flag.kind for flag in tool.flags) or "—",
                            (
                                len(tool.emitted_text)
                                if tool.emitted_text is not None
                                else None
                            ),
                            (
                                len(tool.excerpt_text)
                                if tool.excerpt_text is not None
                                else None
                            ),
                        ),
                    )
                ),
            )
            rows = [tool_evidence(tool, flag) for flag in tool.flags or (None,)]
            self.evidence[self.tool_table][item] = [
                row for row in rows if row is not None
            ]
        if self.visible_tools:
            self.tool_table.selection_set("0")
            self.tool_table.focus("0")
        self.show_tool_detail()

    def show_tool_detail(self, _event=None):
        selection = self.tool_table.selection()
        if not selection:
            self.tool_note.set(
                "No tool results grouped with this call."
                if self.active_call
                else "No tool result selected."
            )
            self.set_preview(self.emitted, "Emitted result", None)
            self.set_preview(self.excerpt, "Excerpt in next matching request", None)
            return
        tool = self.visible_tools[int(selection[0])]
        detail = [flag.detail for flag in tool.flags]
        if tool.excerpt_scope == "containing code cell":
            detail.append(
                "The model-visible excerpt belongs to the containing code cell and may include other tool results."
            )
        identity = tool.tool_call_id or tool.model_visible_call_id
        if identity:
            detail.insert(0, f"Tool call {identity}.")
        self.tool_note.set(" ".join(detail))
        emitted_label = "Emitted result"
        if tool.emitted_payload:
            emitted_label += f" · event #{tool.emitted_payload.sequence}"
        excerpt_label = "Excerpt in next matching request"
        if tool.request_payload:
            excerpt_label += f" · event #{tool.request_payload.sequence}"
        self.set_preview(self.emitted, emitted_label, tool.emitted_text)
        self.set_preview(self.excerpt, excerpt_label, tool.excerpt_text)

    @staticmethod
    def set_preview(preview, label, value):
        heading, widget = preview
        heading.set(label)
        if value is None:
            text = "Unavailable in the capture."
        elif not value:
            text = "(empty)"
        elif len(value) > PREVIEW_CHARACTERS:
            half = PREVIEW_CHARACTERS // 2
            text = (
                value[:half]
                + f"\n\n[Preview omits {len(value) - PREVIEW_CHARACTERS:,} characters]\n\n"
                + value[-half:]
            )
        else:
            text = value
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text.encode("utf-8", "backslashreplace").decode("utf-8"))
        widget.configure(state="disabled")

    def reported_usage(self):
        if self.active_call and self.active_call.response:
            evidence = usage_evidence(self.active_call)
            if any(value is not None for _, value in evidence.counts):
                return evidence
        return None

    def copy_usage(self):
        evidence = self.reported_usage()
        if evidence:
            self.copy([evidence])

    def copy_selected(self, table):
        selection = table.selection()
        rows = self.evidence[table].get(selection[0]) if selection else None
        if rows:
            self.copy(rows)
        return "break"

    def copy(self, rows):
        self.window.clipboard_clear()
        self.window.clipboard_append(markdown_evidence(rows))
        self.status.set(
            f"Copied {len(rows):,} evidence {'row' if len(rows) == 1 else 'rows'} as Markdown"
        )
