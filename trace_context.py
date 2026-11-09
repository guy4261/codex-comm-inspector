"""Break down the text present in a recorded model request."""

import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass

TOOL_OUTPUT_TYPES = {
    "function_call_output",
    "custom_tool_call_output",
    "local_shell_call_output",
    "shell_call_output",
    "apply_patch_call_output",
    "mcp_call_output",
}
OPAQUE_SOURCE = "Opaque or encoded"
CURRENT_RESULTS = "Current tool results"
OPAQUE_FIELDS = (
    "encrypted_content",
    "image_url",
    "file_data",
    "file_url",
    "audio",
    "input_audio",
    "b64_json",
)
DATA_URL = re.compile(r"\Adata:[^\s,]*,")
SKILL_BLOCK = re.compile(r"<skills_instructions>.*?</skills_instructions>", re.DOTALL)
HEADING = re.compile(r"^(#{1,6})[ \t]+([^\r\n]+?)[ \t]*$", re.MULTILINE)
SCAFFOLDING = (
    "# AGENTS.md instructions",
    "<environment_context>",
    "<external_codex_apps_",
)


@dataclass(frozen=True)
class ContextRow:
    source: str
    chars: int
    tokens: int | None
    new_chars: int | None
    new_tokens: int | None
    repeated_chars: int | None
    repeated_tokens: int | None


def request_items(request: dict) -> list:
    items = request.get("input")
    return items if isinstance(items, list) else []


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text_parts(
    value: object, *, structured: bool = False
) -> Iterator[tuple[bool, str]]:
    """Yield (opaque, text) for decoded content parts and known blob fields."""
    if isinstance(value, str):
        if value:
            yield bool(DATA_URL.match(value)), value
    elif isinstance(value, list):
        for part in value:
            yield from _text_parts(part, structured=structured)
    elif isinstance(value, dict):
        opaque_fields = OPAQUE_FIELDS
        if value.get("type") in ("base64", "input_audio", "input_image", "input_file"):
            opaque_fields += ("data",)
        present = [key for key in opaque_fields if value.get(key)]
        for key in present:
            data = value[key]
            yield True, data if isinstance(data, str) else _compact_json(data)

        readable = [
            key for key in ("text", "refusal", "content", "summary") if key in value
        ]
        for key in readable:
            yield from _text_parts(value[key], structured=structured)
        if structured and not present and not readable and value:
            yield False, _compact_json(value)


def _instruction_parts(text: str) -> Iterator[tuple[str, str]]:
    """Separate tagged catalogs and recognizable Markdown skill sections."""
    blocks = list(SKILL_BLOCK.finditer(text))
    if blocks:
        start = 0
        for block in blocks:
            yield from _instruction_parts(text[start : block.start()])
            yield "Skill catalog", block.group()
            start = block.end()
        yield from _instruction_parts(text[start:])
        return

    headings = list(HEADING.finditer(text))
    start = 0
    for index, heading in enumerate(headings):
        if heading.start() < start or heading[2].casefold() not in (
            "skills",
            "available skills",
        ):
            continue
        end = next(
            (
                later.start()
                for later in headings[index + 1 :]
                if len(later[1]) <= len(heading[1])
            ),
            len(text),
        )
        if start < heading.start():
            yield "Instructions", text[start : heading.start()]
        yield "Skill catalog", text[heading.start() : end]
        start = end
    if start < len(text):
        yield "Instructions", text[start:]


def _user_message(item: object) -> bool:
    if not isinstance(item, dict) or item.get("role") != "user":
        return False
    text = [part for _, part in _text_parts(item.get("content"))]
    return not text or any(not part.lstrip().startswith(SCAFFOLDING) for part in text)


def _segments(request: dict) -> Iterator[tuple[str, str, str]]:
    """Yield a displayed source, stable comparison source, and decoded text."""
    items = request_items(request)
    last_user = next(
        (
            index
            for index in range(len(items) - 1, -1, -1)
            if _user_message(items[index])
        ),
        -1,
    )
    instruction = request.get("instructions")
    if isinstance(instruction, str):
        for source, part in _instruction_parts(instruction):
            yield source, source, part

    schemas = request.get("tools")
    if isinstance(schemas, list):
        for schema in schemas:
            yield "Tool schemas", "Tool schemas", _compact_json(schema)

    if isinstance(request.get("input"), str):
        for opaque, part in _text_parts(request["input"]):
            source = OPAQUE_SOURCE if opaque else "History"
            yield source, source, part
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            for opaque, part in _text_parts(item):
                source = OPAQUE_SOURCE if opaque else "History"
                yield source, source, part
            continue
        kind, role = item.get("type"), item.get("role")
        if kind == "additional_tools" and isinstance(item.get("tools"), list):
            for schema in item["tools"]:
                yield "Tool schemas", "Tool schemas", _compact_json(schema)
        if isinstance(kind, str) and kind in TOOL_OUTPUT_TYPES:
            for opaque, part in _text_parts(item.get("output"), structured=True):
                source = CURRENT_RESULTS if index > last_user else "History"
                if opaque:
                    yield OPAQUE_SOURCE, OPAQUE_SOURCE, part
                else:
                    yield source, "tool result", part
        for key in (
            "content",
            "summary",
            "text",
            "refusal",
            "arguments",
            "input",
            *OPAQUE_FIELDS,
        ):
            value = item.get(key)
            if key in OPAQUE_FIELDS and value:
                yield OPAQUE_SOURCE, OPAQUE_SOURCE, (
                    value if isinstance(value, str) else _compact_json(value)
                )
                continue
            for opaque, part in _text_parts(value):
                if opaque:
                    yield OPAQUE_SOURCE, OPAQUE_SOURCE, part
                elif role in ("system", "developer") or (
                    role == "user"
                    and part.lstrip().startswith("# AGENTS.md instructions")
                ):
                    for source, fragment in _instruction_parts(part):
                        yield source, source, fragment
                else:
                    yield "History", "History", part


def _measure(
    parts: list[str], count: Callable[[str], int] | None
) -> tuple[int, int | None]:
    return sum(map(len, parts)), sum(count(part) for part in parts) if count else None


def context_breakdown(
    request: dict,
    previous: dict | None,
    count: Callable[[str], int] | None,
) -> list[ContextRow]:
    """Rank the supplied request's content. The caller chooses the snapshot scope.

    Repetition matches whole decoded parts, including multiplicity, within a source.
    Historical tool results can match current tool results. Character counts use
    decoded Unicode code points. Token counts sum independently counted parts.
    """
    available = (
        Counter((category, part) for _, category, part in _segments(previous))
        if previous is not None
        else {}
    )
    grouped = defaultdict(lambda: ([], []))
    for source, category, part in _segments(request):
        new, repeated = grouped[source]
        key = (category, part)
        if available.get(key, 0):
            repeated.append(part)
            available[key] -= 1
        else:
            new.append(part)

    rows = []
    for source, (new, repeated) in grouped.items():
        new_chars, new_tokens = _measure(new, count)
        repeated_chars, repeated_tokens = _measure(repeated, count)
        tokens = (
            new_tokens + repeated_tokens
            if new_tokens is not None and repeated_tokens is not None
            else None
        )
        rows.append(
            ContextRow(
                source,
                new_chars + repeated_chars,
                tokens,
                new_chars if previous is not None else None,
                new_tokens if previous is not None else None,
                repeated_chars if previous is not None else None,
                repeated_tokens if previous is not None else None,
            )
        )
    if all(row.tokens is not None for row in rows):
        return sorted(rows, key=lambda row: (-row.tokens, row.source))
    return sorted(rows, key=lambda row: (-row.chars, row.source))
