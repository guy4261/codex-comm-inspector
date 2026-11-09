"""Associate Codex trace sidecars with their recorded inference and tool calls."""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from codex_trace import _payload_refs, _trace_path, read_trace_payload


@dataclass(frozen=True)
class Payload:
    trace_id: str
    sequence: int
    path: str
    raw_payload_id: str
    kind: str
    raw_bytes: int | None
    raw_chars: int | None
    document: object


@dataclass(frozen=True)
class TraceEvent:
    trace_id: str
    sequence: int
    thread_id: str
    turn_id: str
    kind: str
    data: dict
    payloads: tuple[Payload, ...]


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    uncached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ModelCall:
    call_id: str
    thread_id: str
    turn_id: str
    model: str
    request: Payload | None
    response: Payload | None
    tools: tuple[TraceEvent, ...]
    usage: Usage
    duplicate_count: int
    status: str
    other_payloads: tuple[Payload, ...] = ()

    @property
    def previous_response_id(self) -> str:
        request = _object(self.request.document) if self.request else {}
        return _identifier(request.get("previous_response_id"))

    @property
    def delta(self) -> bool:
        return bool(self.previous_response_id)


@dataclass(frozen=True)
class TraceAnalysis:
    trace_id: str
    calls: tuple[ModelCall, ...]
    events: tuple[TraceEvent, ...]


def _object(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _identifier(value: object) -> str:
    return value if isinstance(value, str) else ""


def _count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _usage(response: Payload | None, event_data: dict) -> Usage:
    document = _object(response.document) if response else {}
    reported = _object(
        document.get("token_usage")
        or document.get("usage")
        or event_data.get("token_usage")
    )
    input_tokens = _count(reported.get("input_tokens"))
    cached = _count(reported.get("cached_input_tokens"))
    if cached is None:
        cached = _count(
            _object(reported.get("input_tokens_details")).get("cached_tokens")
        )
    uncached = _count(reported.get("uncached_input_tokens"))
    if (
        uncached is None
        and input_tokens is not None
        and cached is not None
        and cached <= input_tokens
    ):
        uncached = input_tokens - cached
    reasoning = _count(reported.get("reasoning_output_tokens"))
    if reasoning is None:
        reasoning = _count(
            _object(reported.get("output_tokens_details")).get("reasoning_tokens")
        )
    return Usage(
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        uncached_input_tokens=uncached,
        output_tokens=_count(reported.get("output_tokens")),
        reasoning_tokens=reasoning,
        total_tokens=_count(reported.get("total_tokens")),
    )


def _response_output(response: Payload) -> object:
    document = _object(response.document)
    return document.get("output_items", document.get("output"))


def _load_payload(root: Path, trace_id: str, sequence: int, reference: dict) -> Payload:
    path = reference["path"].replace("\\", "/")
    kind = _identifier(_object(reference.get("kind")).get("type")) or "trace payload"
    raw_chars = raw_bytes = document = None
    try:
        raw, raw_bytes = read_trace_payload(root, path)
        raw_chars = len(raw)
        document = json.loads(raw.removeprefix("\ufeff"))
    except (OSError, RuntimeError, ValueError):
        pass
    return Payload(
        trace_id,
        sequence,
        path,
        reference["raw_payload_id"],
        kind,
        raw_bytes,
        raw_chars,
        document,
    )


def _read_events(root: Path) -> tuple[str, list[TraceEvent]]:
    trace_id = ""
    try:
        manifest = json.loads(
            _trace_path(root, "manifest.json").read_text(encoding="utf-8-sig")
        )
        trace_id = _identifier(_object(manifest).get("trace_id"))
    except (OSError, RuntimeError, ValueError):
        pass

    events = []
    path = _trace_path(root, "trace.jsonl")
    with path.open(
        encoding="utf-8-sig", errors="backslashreplace", newline=""
    ) as source:
        for line_number, line in enumerate(source, 1):
            try:
                entry = _object(json.loads(line))
            except (ValueError, RecursionError):
                continue
            data = _object(entry.get("payload"))
            kind = _identifier(data.get("type"))
            if kind == "rollout_started":
                trace_id = trace_id or _identifier(data.get("trace_id"))
            if not kind.startswith(
                ("inference_", "compaction_", "tool_call_", "code_cell_")
            ) and kind not in {
                "mcp_tool_call_correlation_assigned",
                "stdin_target_resolved",
            }:
                continue
            sequence = _count(entry.get("seq"))
            if sequence is None:
                sequence = line_number
            payloads = tuple(
                _load_payload(root, trace_id or root.name, sequence, reference)
                for reference in _payload_refs(data)
            )
            events.append(
                TraceEvent(
                    trace_id or root.name,
                    sequence,
                    _identifier(entry.get("thread_id"))
                    or _identifier(data.get("thread_id")),
                    _identifier(entry.get("codex_turn_id"))
                    or _identifier(data.get("codex_turn_id")),
                    kind,
                    data,
                    payloads,
                )
            )
    return trace_id or root.name, events


def _same_payload(first: Payload, second: Payload) -> bool:
    return (
        first.path == second.path
        or bool(first.raw_payload_id and first.raw_payload_id == second.raw_payload_id)
        or (first.document is not None and first.document == second.document)
    )


@dataclass
class _CallEvents:
    thread_id: str = ""
    turn_id: str = ""
    model: str = ""
    status: str = ""
    response_data: dict = field(default_factory=dict)
    requests: list[Payload] = field(default_factory=list)
    responses: list[Payload] = field(default_factory=list)
    tools: list[TraceEvent] = field(default_factory=list)
    duplicate_count: int = 0

    def add(self, event: TraceEvent) -> None:
        self.thread_id = self.thread_id or event.thread_id
        self.turn_id = self.turn_id or event.turn_id
        self.model = self.model or _identifier(event.data.get("model"))
        self.status = event.kind.partition("_")[2]
        for payload in event.payloads:
            if payload.kind in {"inference_request", "compaction_request"}:
                related = self.requests
            elif payload.kind in {"inference_response", "compaction_response"}:
                related = self.responses
            else:
                continue
            if any(_same_payload(previous, payload) for previous in related):
                self.duplicate_count += 1
            else:
                related.append(payload)
        if "token_usage" in event.data:
            self.response_data = event.data


def _group_tools(events: list[TraceEvent], groups: dict[str, _CallEvents]) -> None:
    owners = {}
    for group in groups.values():
        for response in group.responses:
            items = _response_output(response)
            if isinstance(items, list):
                for item in items:
                    call_id = _identifier(_object(item).get("call_id"))
                    if call_id:
                        owners[group.thread_id, call_id] = group

    cells = {}
    for event in events:
        if event.kind == "code_cell_started":
            cell = _identifier(event.data.get("runtime_cell_id"))
            call_id = _identifier(event.data.get("model_visible_call_id"))
            if cell and call_id:
                cells[event.thread_id, cell] = call_id

    tool_ids = {}
    seen_stages = defaultdict(list)
    for event in events:
        tool_id = _identifier(event.data.get("tool_call_id"))
        cell = _identifier(event.data.get("runtime_cell_id"))
        call_id = _identifier(event.data.get("model_visible_call_id"))
        if event.kind == "tool_call_started":
            cell = _identifier(
                _object(event.data.get("requester")).get("runtime_cell_id")
            )
            call_id = call_id or cells.get((event.thread_id, cell), "")
            if tool_id:
                tool_ids[event.thread_id, tool_id] = call_id
        elif event.kind == "tool_call_ended":
            call_id = call_id or tool_ids.get((event.thread_id, tool_id), "")
        elif event.kind in {"code_cell_initial_response", "code_cell_ended"}:
            call_id = call_id or cells.get((event.thread_id, cell), "")
        else:
            continue

        group = owners.get((event.thread_id, call_id))
        if group is None or not event.payloads:
            continue
        stage = "invocation" if event.kind == "tool_call_started" else "result"
        previous_stages = seen_stages[event.thread_id, call_id, cell, tool_id, stage]
        if any(
            len(event.payloads) == len(previous.payloads)
            and all(
                _same_payload(left, right)
                for left, right in zip(event.payloads, previous.payloads)
            )
            for previous in previous_stages
        ):
            group.duplicate_count += 1
            continue
        previous_stages.append(event)
        group.tools.append(event)


def load_trace_analysis(path: Path) -> TraceAnalysis:
    """Load the model and tool lifecycle evidence from a trace directory or entry point."""
    if path.is_dir():
        root = path.resolve()
    elif path.name in {"manifest.json", "trace.jsonl"}:
        root = path.parent.resolve()
    else:
        raise ValueError("Select a Codex trace folder, manifest.json, or trace.jsonl.")
    trace_id, events = _read_events(root)
    groups = {}
    for event in events:
        if event.kind.startswith(("inference_", "compaction_")):
            call_id = _identifier(
                event.data.get("inference_call_id")
                or event.data.get("compaction_call_id")
            )
            if call_id:
                groups.setdefault(call_id, _CallEvents()).add(event)
    _group_tools(events, groups)

    calls = []
    for call_id, group in groups.items():
        request = group.requests[0] if group.requests else None
        response = group.responses[-1] if group.responses else None
        document = _object(request.document) if request else {}
        calls.append(
            ModelCall(
                call_id=call_id,
                thread_id=group.thread_id,
                turn_id=group.turn_id,
                model=group.model or _identifier(document.get("model")),
                request=request,
                response=response,
                tools=tuple(group.tools),
                usage=_usage(response, group.response_data),
                duplicate_count=group.duplicate_count,
                status=group.status,
                other_payloads=tuple(group.requests[1:] + group.responses[:-1]),
            )
        )
    return TraceAnalysis(trace_id, tuple(calls), tuple(events))
