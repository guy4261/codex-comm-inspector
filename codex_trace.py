"""Read the experimental local Codex rollout trace and its payload sidecars."""

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from records import Record, Source
from source_titles import first_user_title, project_name, prompt_title, source_title

TRACE_COVERAGE = (
    "Experimental local Codex trace. Shows recorded model request snapshots, response data, "
    "tool activity, and lifecycle events where available. Coverage ends at the local Codex harness."
)

TRACE_DIRECTIONS = {
    "inference_request": "input",
    "compaction_request": "input",
    "inference_response": "output",
    "compaction_response": "output",
}
TITLE_METADATA_BYTES = 256 * 1024
TITLE_STARTUP_LINES = 32


def list_traces(root: Path, thread_labels=None) -> list[Source]:
    root = root.resolve()
    traces = []
    for directory in root.glob("trace-*"):
        try:
            resolved = directory.resolve(strict=True)
            if resolved.parent == root and resolved.is_dir():
                event_log = _trace_path(resolved, "trace.jsonl")
                traces.append((event_log.stat().st_mtime, event_log))
        except (OSError, RuntimeError, ValueError):
            continue
    return [
        trace_source(path, thread_labels) for _, path in sorted(traces, reverse=True)
    ]


def trace_source(path: Path, thread_labels=None) -> Source:
    if path.name not in {"manifest.json", "trace.jsonl"}:
        raise ValueError("Select a Codex trace folder's manifest.json or trace.jsonl.")
    root = path.parent.resolve()
    return Source(
        title=_trace_title(root, thread_labels or {}),
        coverage=f"{TRACE_COVERAGE}\n{root}",
        load=lambda: _read_trace(root),
        trace_path=root / "trace.jsonl",
    )


def _trace_path(root: Path, value: str) -> Path:
    # Codex stores relative paths. Reject drive names, alternate streams, and traversal.
    name = value.replace("\\", "/")
    parts = name.split("/")
    if ":" in name or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Trace payload path is not a safe relative path.")
    path = root.joinpath(*parts).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Trace payload path is outside the trace or is not a file.")
    return path


def _trace_payload_path(root: Path, name: str) -> Path:
    """Resolve a sidecar inside the trace's payload directory."""
    name = name.replace("\\", "/")
    if not name.startswith("payloads/"):
        raise ValueError("Trace sidecar is outside the payload directory.")
    path = _trace_path(root, name)
    if not path.is_relative_to(root / "payloads"):
        raise ValueError("Resolved trace sidecar is outside the payload directory.")
    return path


def read_trace_payload(root: Path, name: str) -> tuple[str, int]:
    data = _trace_payload_path(root, name).read_bytes()
    return data.decode("utf-8", errors="backslashreplace"), len(data)


def _json_object(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def _title_metadata(path: Path) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(TITLE_METADATA_BYTES + 1)
    return _json_object(raw) if len(raw) <= TITLE_METADATA_BYTES else {}


def _startup_events(root: Path) -> list[dict]:
    # Title discovery only needs the small startup prefix of a trace.
    try:
        with _trace_path(root, "trace.jsonl").open("rb") as stream:
            lines = stream.read(TITLE_METADATA_BYTES).splitlines()[:TITLE_STARTUP_LINES]
    except (OSError, RuntimeError, ValueError):
        return []
    return [
        event
        for line in lines
        if isinstance((event := _json_object(line)).get("payload"), dict)
    ]


def _thread_key(value) -> str:
    return value.casefold() if isinstance(value, str) else ""


def _startup_metadata(root: Path, reference) -> dict:
    name = reference.get("path") if isinstance(reference, dict) else None
    if not isinstance(name, str):
        return {}
    try:
        return _title_metadata(_trace_payload_path(root, name))
    except (OSError, RuntimeError, ValueError):
        return {}


def _trace_details(root, startup, thread_id, title, project):
    for event in startup:
        payload = event["payload"]
        if _thread_key(event.get("thread_id") or payload.get("thread_id")) != thread_id:
            continue
        if not project and payload.get("type") == "thread_started":
            metadata = _startup_metadata(root, payload.get("metadata_payload"))
            project = project_name(metadata.get("cwd"))
        elif not title and payload.get("type") == "inference_started":
            request = _startup_metadata(root, payload.get("request_payload"))
            content = request.get("input")
            title = (
                prompt_title(content)
                if isinstance(content, str)
                else first_user_title(content)
            )
        if title and project:
            break
    return title, project


def _trace_title(root: Path, thread_labels) -> str:
    try:
        manifest = _title_metadata(_trace_path(root, "manifest.json"))
    except (OSError, RuntimeError, ValueError):
        manifest = {}
    thread_id = _thread_key(manifest.get("root_thread_id"))
    label = thread_labels.get(thread_id)
    reference = f"Codex trace · {root.name}"
    if label and label.title and label.project:
        return source_title(label.title, project=label.project, reference=reference)

    startup = _startup_events(root)
    if not thread_id:
        start = next(
            (
                event["payload"]
                for event in startup
                if event["payload"].get("type") == "rollout_started"
            ),
            {},
        )
        thread_id = _thread_key(start.get("root_thread_id"))
        label = thread_labels.get(thread_id)
    title, project = (label.title, label.project) if label else ("", "")
    if thread_id:
        title, project = _trace_details(root, startup, thread_id, title, project)
    return source_title(title, project=project, reference=reference)


def _timestamp(value) -> str:
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat(
            timespec="milliseconds"
        )
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _payload_refs(value: object) -> Iterator[dict]:
    pending = [value]
    while pending:
        child = pending.pop()
        if isinstance(child, dict):
            if isinstance(child.get("raw_payload_id"), str) and isinstance(
                child.get("path"), str
            ):
                yield child
            else:
                pending.extend(reversed(list(child.values())))
        elif isinstance(child, list):
            pending.extend(reversed(child))


def _read_trace(root: Path) -> Iterator[Record]:
    try:
        manifest_path = _trace_path(root, "manifest.json")
    except FileNotFoundError:
        pass
    else:
        with manifest_path.open(
            encoding="utf-8", errors="backslashreplace", newline=""
        ) as file:
            raw = file.read()
        yield Record("trace manifest", root.name, raw, direction="local")

    event_path = _trace_path(root, "trace.jsonl")
    with event_path.open(
        encoding="utf-8", errors="backslashreplace", newline=""
    ) as file:
        for line_number, line in enumerate(file, 1):
            try:
                event = json.loads(line)
            except ValueError:
                yield Record(
                    "unparsed trace event",
                    f"Line {line_number}",
                    line,
                    direction="local",
                )
                continue
            if not isinstance(event, dict):
                yield Record(
                    "trace value", f"Line {line_number}", line, direction="local"
                )
                continue

            payload = event.get("payload")
            event_kind = (
                str(payload.get("type") or "trace event")
                if isinstance(payload, dict)
                else "trace event"
            )
            sequence = event.get("seq", line_number)
            timestamp = _timestamp(event.get("wall_time_unix_ms"))
            yield Record(
                event_kind, f"#{sequence} · {event_kind}", line, timestamp, "local"
            )

            for reference in _payload_refs(payload):
                kind = reference.get("kind")
                label = (
                    str(kind.get("type") or "trace payload")
                    if isinstance(kind, dict)
                    else "trace payload"
                )
                name = reference["path"].replace("\\", "/")
                try:
                    raw, _ = read_trace_payload(root, name)
                except (OSError, RuntimeError, ValueError):
                    yield Record(
                        "unavailable trace payload",
                        f"#{sequence} · {label}",
                        name,
                        timestamp,
                        "local",
                    )
                    continue
                yield Record(
                    label,
                    f"#{sequence} · {name}",
                    raw,
                    timestamp,
                    TRACE_DIRECTIONS.get(label, "local"),
                )
