"""Match emitted tool results to the first recorded model request carrying them."""

import json
import re
import shlex
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trace_calls import Payload, TraceEvent


LONG_LINE_CHARS = 3000
_FAILURE = {"error", "failed", "timed_out", "timeout", "denied"}
_OUTPUT_ITEMS = {"function_call_output", "custom_tool_call_output", "tool_result"}
_SEARCH = re.compile(
    r"(?:^|[;|&\n])\s*(rg|ripgrep|grep|git grep|find|findstr|get-childitem)\b([^;|&\n]*)",
    re.I,
)
_LIMITED_PIPE = re.compile(
    r"\|\s*(?:head\b|select-object\s+-first\b|select\s+-first\b)", re.I
)
_OUTPUT_HEADER = re.compile(
    r"^Wall time:[^\r\n]*\r?\n(?:[ \t]*\r?\n)*Output:[ \t]*\r?\n", re.I
)
_TRUNCATION = re.compile(
    r"(?im)(?:^[ \t]*(?:\[|\.{3}|…)[^\n]{0,50}\btruncat(?:ed|ion)\b[^\n]{0,100}(?:\]|\.{3}|…)[ \t\r]*$"
    r"|\b(?:omitted|truncated)\s+[\d,]+\s+(?:tokens|characters|bytes|lines)\b"
    r"|\b[\d,]+\s+(?:tokens|characters|bytes|lines)\s+(?:omitted|truncated)\b)"
)


@dataclass(frozen=True)
class DiagnosticFlag:
    kind: str
    detail: str
    related_payload: "Payload | None" = None


@dataclass(frozen=True)
class ToolDiagnostic:
    tool_call_id: str
    model_visible_call_id: str | None
    inference_call_id: str | None
    tool_name: str
    status: str
    emitted_payload: "Payload | None"
    request_payload: "Payload | None"
    next_inference_call_id: str | None
    emitted_text: str | None
    excerpt_text: str | None
    excerpt_scope: str | None
    longest_line_chars: int
    flags: tuple[DiagnosticFlag, ...]


@dataclass
class _Execution:
    identifier: str
    thread_id: str
    turn_id: str
    name: str
    arguments: object
    model_id: str | None
    start_index: int
    cell_id: str | None = None
    invocation: "Payload | None" = None
    runtime: "Payload | None" = None
    runtime_index: int = -1
    result: "Payload | None" = None
    result_index: int = -1
    end_index: int = -1
    status: str = ""
    runtime_status: str = ""
    exit_code: int | None = None
    explicit_failure: bool = False
    cell: bool = False


@dataclass(frozen=True)
class _Excerpt:
    index: int
    call_id: str | None
    payload: "Payload"
    text: str
    truncated: bool


def _obj(value):
    return value if isinstance(value, dict) else {}


def _array(value):
    return value if isinstance(value, list) else []


def _identifier(value):
    return value if isinstance(value, str) and value else None


def _payload(event, field):
    raw_id = _obj(event.data.get(field)).get("raw_payload_id")
    if raw_id is None:
        return None
    return next(
        (payload for payload in event.payloads if payload.raw_payload_id == raw_id),
        None,
    )


def _document(payload):
    return _obj(payload.document) if payload else {}


def _arguments(invocation):
    body = _obj(invocation.get("payload"))
    arguments = body.get("arguments", body.get("input"))
    if isinstance(arguments, str):
        try:
            return json.loads(arguments)
        except ValueError:
            pass
    return arguments


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [
            item if isinstance(item, str) else _obj(item).get("text") for item in value
        ]
        strings = [part for part in parts if isinstance(part, str)]
        return "\n".join(strings) if strings or not value else None
    return None


def _emitted_text(document):
    if "response_item" in document:
        return _text(_obj(document["response_item"]).get("output"))
    if "response" in document:
        result = _obj(_obj(document["response"]).get("Result"))
        text = _text(result.get("content_items"))
        error = _text(result.get("error_text"))
        return "\n".join(part for part in (text, error) if part) if error else text
    value = document.get("value", document)
    if isinstance(value, dict) and "output" in value:
        return _text(value["output"])
    return _text(value)


def _explicit_truncation(value):
    data = _obj(value)
    return (
        data.get("truncated") is True
        or data.get("is_truncated") is True
        or any(
            _explicit_truncation(data[key])
            for key in ("value", "response_item")
            if key in data
        )
    )


def _command(arguments):
    if isinstance(arguments, str):
        return arguments
    cmd = _obj(arguments).get("cmd", _obj(arguments).get("command"))
    if isinstance(cmd, list) and all(isinstance(arg, str) for arg in cmd):
        return shlex.join(cmd)
    return cmd if isinstance(cmd, str) else ""


def _broad_search(arguments, emitted_chars):
    queries = _array(_obj(arguments).get("search_query"))
    if (
        len(queries) >= 2
        and all(not _obj(query).get("domains") for query in queries)
        and (len(queries) >= 3 or emitted_chars >= 12_000)
    ):
        return True
    command = _command(arguments)
    if _LIMITED_PIPE.search(command):
        return False
    for match in _SEARCH.finditer(command):
        verb, arguments_text = match.groups()
        try:
            args = [
                word.strip("\"'") for word in shlex.split(arguments_text, posix=False)
            ]
        except ValueError:
            continue
        verb = verb.lower()
        if verb == "get-childitem":
            positional_paths = [arg for arg in args if not arg.startswith("-")]
            filters = re.search(
                r"(?i)\s-(?:filter|include|exclude|depth)\b", arguments_text
            )
            if (
                "-recurse" in [arg.lower() for arg in args]
                and not filters
                and (
                    not positional_paths
                    or any(_open_root(path) for path in positional_paths)
                )
            ):
                return True
            continue
        if verb == "find":
            if not args or _open_root(args[0]):
                return True
            continue
        recursive = verb in {"rg", "ripgrep", "git grep"} or any(
            arg in {"-r", "-R", "--recursive", "/s", "/S"} for arg in args
        )
        if not recursive:
            continue
        if any(
            re.match(
                r"^(?:-g|--glob|-t|--type|--include|--exclude|--max-count|-m\d)", arg
            )
            for arg in args
        ):
            continue
        positionals = [arg for arg in args if not arg.startswith("-")]
        paths = (
            positionals
            if "--files" in args or "-e" in args or "--regexp" in args
            else positionals[1:]
        )
        if "-e" in args or "--regexp" in args:
            expressions = {
                args[i + 1]
                for i, arg in enumerate(args[:-1])
                if arg in {"-e", "--regexp"}
            }
            paths = [arg for arg in paths if arg not in expressions]
        if not paths or any(_open_root(path) for path in paths):
            return True
    return False


def _open_root(path):
    return path in {".", "*", "/", "\\", "./", ".\\", "~"} or bool(
        re.fullmatch(r"[A-Za-z]:[/\\]?", path)
    )


def _search_without_matches(execution):
    if execution.exit_code != 1:
        return False
    command = _command(execution.arguments)
    return bool(
        re.match(r"\s*(?:rg|ripgrep|grep|git[ \t]+grep)(?=[ \t]|$)", command, re.I)
    ) and not re.search(r"[;|&\r\n]", command.strip())


def _failed(execution):
    statuses = {execution.status.lower(), execution.runtime_status.lower()}
    if execution.explicit_failure or statuses & (_FAILURE - {"failed"}):
        return True
    if _search_without_matches(execution):
        return False
    return (
        "failed" in statuses
        or type(execution.exit_code) is int
        and execution.exit_code != 0
    )


def _similar_arguments(first, second):
    if first is None or second is None:
        return False
    if first == second:
        return True
    left_cmd, right_cmd = _command(first), _command(second)
    if left_cmd and right_cmd:
        left, right = " ".join(left_cmd.split()), " ".join(right_cmd.split())
        if left.split(maxsplit=1)[:1] != right.split(maxsplit=1)[:1]:
            return False
    else:
        left = json.dumps(first, sort_keys=True, ensure_ascii=False)
        right = json.dumps(second, sort_keys=True, ensure_ascii=False)
    if left == right:
        return bool(left)
    if not (min(len(left), len(right)) >= 8 and max(len(left), len(right)) <= 4096):
        return False
    matcher = SequenceMatcher(None, left, right, autojunk=False)
    return matcher.quick_ratio() >= 0.82 and matcher.ratio() >= 0.82


def _is_excerpt(emitted, excerpt):
    if not emitted or not excerpt:
        return False
    candidate = _OUTPUT_HEADER.sub("", excerpt).strip()
    original = emitted.strip()
    return 64 <= len(candidate) < len(original) - 32 and original.startswith(candidate)


def _record_request(event, index, excerpts):
    payload = _payload(event, "request_payload")
    for item in _array(_document(payload).get("input")):
        item = _obj(item)
        model_id = _identifier(item.get("call_id"))
        if model_id is None or _identifier(item.get("type")) not in _OUTPUT_ITEMS:
            continue
        output = _text(item.get("output", item.get("content")))
        if output is not None:
            excerpts[event.thread_id, model_id].append(
                _Excerpt(
                    index, _call_id(event), payload, output, _explicit_truncation(item)
                )
            )


def _call_id(event):
    return _identifier(
        event.data.get("inference_call_id") or event.data.get("compaction_call_id")
    )


def _record_result(execution, event, index, field):
    execution.end_index = index
    execution.status = str(event.data.get("status") or execution.status)
    payload = _payload(event, field)
    document = _document(payload)
    if not payload or (execution.cell and "Yielded" in _obj(document.get("response"))):
        return
    # Preserve the first emission if a final lifecycle event repeats its content.
    text = _emitted_text(document)
    previous = _document(execution.result)
    if (
        execution.result is None
        or document
        and (not previous or text != _emitted_text(previous))
    ):
        execution.result = payload
        execution.result_index = index
    result = _obj(_obj(document.get("response")).get("Result"))
    execution.explicit_failure |= (
        bool(result.get("error_text")) or document.get("is_error") is True
    )
    exit_code = _obj(document.get("value")).get("exit_code")
    if type(exit_code) is int:
        execution.exit_code = exit_code


def _executions_and_excerpts(events):
    tools = {}
    cells = {}
    executions = []
    excerpts = defaultdict(list)
    owners = {}
    for index, event in enumerate(events):
        data = event.data
        thread = event.thread_id
        tool_key = thread, _identifier(data.get("tool_call_id"))
        cell_key = thread, _identifier(data.get("runtime_cell_id"))
        if event.kind in {"inference_started", "compaction_started"}:
            _record_request(event, index, excerpts)
        elif event.kind in {
            "inference_completed",
            "inference_cancelled",
            "inference_failed",
        }:
            response = _payload(event, "response_payload") or _payload(
                event, "partial_response_payload"
            )
            for item in _array(_document(response).get("output_items")):
                model_id = _identifier(_obj(item).get("call_id"))
                if (
                    model_id is not None
                    and _identifier(_obj(item).get("type")) not in _OUTPUT_ITEMS
                ):
                    owners.setdefault((thread, model_id), (_call_id(event), response))
        elif (
            event.kind == "tool_call_started"
            and tool_key[1] is not None
            and tool_key not in tools
        ):
            invocation_payload = _payload(event, "invocation_payload")
            invocation = _document(invocation_payload)
            tool_name = _obj(data.get("summary")).get("label") or invocation.get(
                "tool_name"
            )
            requester = _obj(data.get("requester"))
            execution = _Execution(
                tool_key[1],
                thread,
                event.turn_id,
                str(tool_name or "Tool"),
                _arguments(invocation),
                _identifier(data.get("model_visible_call_id")),
                index,
                cell_id=_identifier(requester.get("runtime_cell_id")),
                invocation=invocation_payload,
            )
            tools[tool_key] = execution
            executions.append(execution)
        elif (
            event.kind == "code_cell_started"
            and cell_key[1] is not None
            and cell_key not in cells
        ):
            execution = _Execution(
                cell_key[1],
                thread,
                event.turn_id,
                "Code cell",
                _identifier(data.get("source_js")),
                _identifier(data.get("model_visible_call_id")),
                index,
                cell=True,
            )
            cells[cell_key] = execution
            executions.append(execution)
        elif event.kind == "tool_call_runtime_ended" and tool_key in tools:
            execution = tools[tool_key]
            execution.runtime = _payload(event, "runtime_payload")
            execution.runtime_index = index
            execution.runtime_status = str(data.get("status") or "")
            execution.exit_code = _document(execution.runtime).get("exit_code")
        elif event.kind == "tool_call_ended" and tool_key in tools:
            _record_result(tools[tool_key], event, index, "result_payload")
        elif (
            event.kind in {"code_cell_initial_response", "code_cell_ended"}
            and cell_key in cells
        ):
            _record_result(cells[cell_key], event, index, "response_payload")
    return executions, cells, excerpts, owners


def _retry_indexes(executions):
    recent = defaultdict(lambda: deque(maxlen=4))
    retried = {}
    for index, execution in enumerate(executions):
        key = execution.thread_id, execution.turn_id, execution.name
        previous = recent[key]
        for prior in reversed(previous):
            failed = executions[prior]
            failure_index = (
                failed.runtime_index
                if failed.runtime_status.lower() in _FAILURE
                else failed.end_index
            )
            if (
                0 <= failure_index < execution.start_index
                and _failed(failed)
                and _similar_arguments(failed.arguments, execution.arguments)
            ):
                retried.setdefault(prior, execution)
                break
        previous.append(index)
    return retried


def diagnose_tools(events: "Iterable[TraceEvent]") -> list[ToolDiagnostic]:
    """Analyze in event order. Associate output only through recorded call IDs."""
    executions, cells, excerpts, owners = _executions_and_excerpts(events)
    retried = _retry_indexes(executions)
    rows = []
    for index, execution in enumerate(executions):
        if execution.end_index < 0:
            continue
        cell = cells.get((execution.thread_id, execution.cell_id))
        model_id = execution.model_id or (cell.model_id if cell else None)
        key = execution.thread_id, model_id
        owner_id, _ = owners.get(key, (None, None))
        excerpt_index = (
            execution.result_index if execution.result else execution.end_index
        )
        excerpt = next(
            (value for value in excerpts.get(key, ()) if value.index > excerpt_index),
            None,
        )
        scope = (
            ("containing code cell" if cell and not execution.model_id else "direct")
            if excerpt
            else None
        )
        emitted = _document(execution.result)
        emitted_text = _emitted_text(emitted)
        longest = max(
            (len(line) for line in (emitted_text or "").splitlines()), default=0
        )
        flags = []
        if longest >= LONG_LINE_CHARS:
            flags.append(
                DiagnosticFlag(
                    "Large single line", f"A line contains {longest:,} characters."
                )
            )
        emitted_chars = len(emitted_text or "")
        code_catalog_search = (
            execution.cell
            and emitted_chars >= 8_000
            and re.search(r"\bALL_TOOLS\b", execution.arguments or "")
        )
        if (
            code_catalog_search
            or not execution.cell
            and _broad_search(execution.arguments, emitted_chars)
        ):
            flags.append(
                DiagnosticFlag(
                    "Broad search", "The search appears to cover an unrestricted scope."
                )
            )
        runtime_text = _text(_document(execution.runtime).get("aggregated_output"))
        if _explicit_truncation(emitted) or _TRUNCATION.search(emitted_text or ""):
            flags.append(
                DiagnosticFlag(
                    "Truncation",
                    "The emitted result contains a truncation field or marker.",
                )
            )
        elif _is_excerpt(runtime_text, emitted_text):
            flags.append(
                DiagnosticFlag(
                    "Truncation",
                    "The emitted result appears to carry a shortened prefix of the runtime output.",
                    execution.runtime,
                )
            )
        elif scope == "direct" and (
            excerpt.truncated or _TRUNCATION.search(excerpt.text)
        ):
            flags.append(
                DiagnosticFlag(
                    "Truncation",
                    "The request output contains a truncation field or marker.",
                )
            )
        elif scope == "direct" and _is_excerpt(emitted_text, excerpt.text):
            flags.append(
                DiagnosticFlag(
                    "Truncation",
                    "The recorded request appears to carry a shortened prefix.",
                )
            )
        if retry := retried.get(index):
            _, retry_response = owners.get(
                (retry.thread_id, retry.model_id), (None, None)
            )
            flags.append(
                DiagnosticFlag(
                    "Failed call retried",
                    "A nearby call to the same tool used similar arguments.",
                    retry.invocation or retry_response,
                )
            )
        if (
            execution.result
            and emitted_text is None
            and execution.result.document is not None
        ):
            emitted_text = json.dumps(
                execution.result.document, indent=2, ensure_ascii=False
            )
        rows.append(
            ToolDiagnostic(
                execution.identifier,
                model_id,
                owner_id,
                execution.name,
                "failed" if _failed(execution) else execution.status,
                execution.result,
                excerpt.payload if excerpt else None,
                excerpt.call_id if excerpt else None,
                emitted_text,
                excerpt.text if excerpt else None,
                scope,
                longest,
                tuple(flags),
            )
        )
    return rows
