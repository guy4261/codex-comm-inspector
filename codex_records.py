"""Read local Codex rollout files without changing the sessions."""

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from codex_metadata import ThreadLabel, read_thread_labels
from records import Record, Source
from source_titles import prompt_title, short_title, source_title

ROLLOUT_COVERAGE = (
    "Codex persisted history. Inspect any prompts, injected messages, tool activity, "
    "settings, usage and reasoning summaries retained in this file. Input and output "
    "labels describe recorded roles. Exact network payloads, server-added context "
    "and private reasoning are outside this record's coverage."
)

ROLLOUT_ID = re.compile(
    r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.jsonl(?:\.zst)?$",
    re.IGNORECASE,
)
TITLE_SCAN_BYTES = 1024 * 1024
TITLE_SCAN_LINES = 80


def codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    return Path(override).expanduser() if override else Path.home() / ".codex"


def list_codex(
    home: Path, thread_labels: dict[str, ThreadLabel] | None = None
) -> list[Source]:
    """List rollouts by activity and fill gaps in the supplied thread labels."""
    labels = read_thread_labels(home) if thread_labels is None else thread_labels
    rollouts = []
    for directory in (home / "sessions", home / "archived_sessions"):
        for path in directory.rglob("rollout-*.jsonl*"):
            if not path.name.lower().endswith((".jsonl", ".jsonl.zst")):
                continue
            try:
                if path.is_file():
                    rollouts.append((path.stat().st_mtime, path))
            except OSError:
                # An active rollout may be renamed during background compression.
                continue

    sources = []
    for _, path in sorted(rollouts, reverse=True):
        thread_id, label = _rollout_title(path, labels)
        if thread_id and (label.title or label.project):
            labels[thread_id] = label
        sources.append(_labeled_source(path, label))
    return sources


def codex_source(
    path: Path, thread_labels: dict[str, ThreadLabel] | None = None
) -> Source:
    _, label = _rollout_title(path, thread_labels or {})
    return _labeled_source(path, label)


def _labeled_source(path, label):
    return Source(
        title=source_title(
            label.title or "Codex session", project=label.project, reference=path.name
        ),
        coverage=f"{ROLLOUT_COVERAGE}\n{path}",
        load=lambda: _read_rollout(path),
        project=label.project,
    )


@contextmanager
def _open_rollout(path: Path):
    if path.suffix.lower() != ".zst":
        with path.open("rb") as stream:
            yield stream
        return
    try:
        from compression import zstd
    except ImportError as exc:
        raise RuntimeError(
            "Python 3.14 or newer is required for .jsonl.zst rollouts."
        ) from exc
    try:
        with zstd.open(path, "rb") as stream:
            yield stream
    except zstd.ZstdError as exc:
        raise OSError(f"Could not decompress {path.name}: {exc}") from exc


def _opening_prompt(kind, payload):
    if kind == "event_msg" and payload.get("type") == "user_message":
        return prompt_title(payload.get("message"))
    if (
        kind != "response_item"
        or payload.get("type") != "message"
        or payload.get("role") != "user"
    ):
        return ""
    return prompt_title(payload.get("content"))


def _rollout_title(path, labels):
    match = ROLLOUT_ID.search(path.name)
    thread_id = match[1].casefold() if match else ""
    indexed = labels.get(thread_id, ThreadLabel())
    title, project = indexed.title, indexed.project
    if title:
        return thread_id, indexed

    remaining = TITLE_SCAN_BYTES
    try:
        with _open_rollout(path) as stream:
            for _ in range(TITLE_SCAN_LINES):
                if not remaining or title:
                    break
                line = stream.readline(remaining)
                if not line:
                    break
                remaining -= len(line)
                try:
                    entry = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if not isinstance(entry, dict):
                    continue
                kind = entry.get("type")
                payload = entry.get("payload")
                if not isinstance(payload, dict):
                    payload = entry.get("item")
                if not isinstance(payload, dict):
                    continue
                if kind == "session_meta":
                    metadata_id = payload.get("id") or payload.get("session_id")
                    if isinstance(metadata_id, str) and metadata_id:
                        thread_id = metadata_id.casefold()
                        if saved := labels.get(thread_id):
                            title = saved.title or title
                            project = saved.project or project
                    title = title or short_title(payload.get("title"))
                title = title or _opening_prompt(kind, payload)
    except (EOFError, OSError, RuntimeError):
        pass
    return thread_id, ThreadLabel(title, project)


def _read_rollout(path: Path) -> Iterator[Record]:
    with _open_rollout(path) as stream:
        for line_number, line in enumerate(stream, 1):
            raw = line.decode("utf-8", errors="backslashreplace")
            try:
                parsed = json.loads(
                    raw.removeprefix("\ufeff") if line_number == 1 else raw
                )
            except ValueError:
                yield Record(
                    "unparsed JSONL",
                    f"Incomplete or invalid JSON at line {line_number}",
                    raw,
                    direction="local",
                )
                continue
            if not isinstance(parsed, dict):
                yield Record(
                    "JSONL value",
                    f"JSON value at line {line_number}",
                    raw,
                    direction="local",
                )
                continue
            yield _rollout_record(parsed, raw)


def _rollout_record(entry: dict, raw: str) -> Record:
    kind = str(entry.get("type") or "JSONL object")
    timestamp = str(entry.get("timestamp") or "")
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        payload = entry.get("item")
    if not isinstance(payload, dict):
        payload = {}
    payload_type = payload.get("type")
    role = payload.get("role")

    direction = "local"
    if kind == "response_item":
        if payload_type == "message":
            if role in ("developer", "system", "user"):
                direction = "input"
            elif role == "assistant":
                direction = "output"
        elif payload_type in (
            "function_call_output",
            "custom_tool_call_output",
            "additional_tools",
        ):
            direction = "input"
        elif payload_type in ("function_call", "custom_tool_call", "reasoning"):
            direction = "output"

    label = " / ".join(str(part) for part in (kind, payload_type, role) if part)
    summary = payload.get("name") or payload.get("model") or payload.get("text")
    if not summary:
        content = payload.get("content")
        if isinstance(content, list):
            summary = next(
                (
                    item["text"]
                    for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                ),
                "",
            )
    summary = " ".join(summary.split()) if isinstance(summary, str) else ""
    if len(summary) > 160:
        summary = summary[:159] + "…"
    return Record(label, summary or label, raw, timestamp, direction)
