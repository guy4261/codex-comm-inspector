"""Read offline ChatGPT exports and client-side captures without modifying them."""

import json
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from functools import partial
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from zipfile import ZipFile

from records import Record, Source
from source_titles import (
    first_user_title,
    project_name,
    prompt_title,
    short_title,
    source_title,
)

CHATGPT_COVERAGE = (
    "ChatGPT data export. Includes all conversation nodes and metadata present in the export, "
    "including alternate branches. Hosted model requests and private reasoning are outside "
    "the scope of the export."
)
HAR_COVERAGE = (
    "Browser HTTP archive. Shows what the browser retained, including request and response "
    "bodies when present. Streaming frames, credentials stripped by the browser, and hosted "
    "model requests may be absent."
)
JSON_COVERAGE = (
    "Imported JSON. Shows the fields in this file. API requests, responses, and input-item "
    "lists reveal only the fields captured or exposed to the API caller."
)
SSE_COVERAGE = (
    "Client-side event stream. Shows the event blocks saved in this file, including metadata "
    "and intermediate events. Only the received data present in the file is available."
)
PREVIEW_COVERAGE = (
    "Codex prompt preview. Shows the local input items Codex assembled for this preview. "
    "This snapshot comes from a local dry run."
)


def _record(
    kind: str, summary: str, value: object, timestamp: str = "", direction: str = ""
) -> Record:
    raw = json.dumps(value, ensure_ascii=False, indent=2)
    raw = raw.encode("utf-8", errors="backslashreplace").decode("utf-8")
    return Record(kind, summary, raw, timestamp, direction)


def _obj(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value: object, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    value = value[:1000].encode("utf-8", errors="backslashreplace").decode("utf-8")
    return " ".join(value.split())[:180] or fallback


def _timestamp(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            return str(value)
    return _text(value)


def _chatgpt_filename(name: str) -> bool:
    name = name.lower()
    return name.startswith("conversations") and name.endswith(".json")


def _chatgpt_prompt(fields: dict) -> str:
    first_title = ""
    first_time = float("inf")
    for node in _obj(fields.get("mapping")).values():
        message = _obj(_obj(node).get("message"))
        if _obj(message.get("author")).get("role") != "user":
            continue
        if _obj(message.get("metadata")).get("is_visually_hidden_from_conversation"):
            continue
        created_at = message.get("create_time")
        timestamp = (
            created_at
            if type(created_at) in (int, float) and created_at == created_at
            else float("inf")
        )
        if first_title and timestamp >= first_time:
            continue
        content = _obj(message.get("content"))
        if title := prompt_title(content.get("parts")) or prompt_title(
            content.get("text")
        ):
            first_title, first_time = title, timestamp
    return first_title


def _capture_project(fields: dict) -> str:
    return (
        short_title(fields.get("project_name"))
        or short_title(_obj(fields.get("project")).get("name"))
        or project_name(fields.get("workspace"))
    )


def _capture_source(
    path: Path,
    title: str,
    coverage: str,
    load: Callable[[], Iterator[Record]],
    *,
    project: str = "",
) -> Source:
    return Source(
        source_title(title, project=project, reference=path.name),
        f"{coverage}\n{path.absolute()}",
        load,
    )


def _chatgpt_records(conversation: object) -> Iterator[Record]:
    fields = _obj(conversation)
    mapping = fields.get("mapping")
    if not isinstance(mapping, dict):
        yield _record("conversation", "Exported conversation", conversation)
        return

    metadata = {key: value for key, value in fields.items() if key != "mapping"}
    yield _record(
        "conversation",
        "Conversation metadata",
        metadata,
        _timestamp(metadata.get("create_time")),
        "metadata",
    )
    for key, node in mapping.items():
        message = _obj(_obj(node).get("message"))
        author = _obj(message.get("author"))
        role = _text(author.get("role"), "node")
        content = _obj(message.get("content"))
        parts = content.get("parts")
        snippet = ""
        if isinstance(parts, list):
            for part in parts:
                snippet = _text(part)
                if snippet:
                    break
        summary = snippet or _text(content.get("text"))
        summary = summary or _text(
            content.get("content_type"), "Conversation graph node"
        )
        direction = {"user": "sent", "assistant": "received"}.get(role, "")
        yield _record(
            role,
            summary,
            {"mapping_key": key, "node": node},
            _timestamp(message.get("create_time")),
            direction,
        )


def _chatgpt_sources(document: object, path: Path) -> Iterator[Source]:
    conversations = document if isinstance(document, list) else [document]
    for index, conversation in enumerate(conversations, 1):
        fields = _obj(conversation)
        title = (
            short_title(fields.get("title"))
            or _chatgpt_prompt(fields)
            or f"Untitled conversation {index}"
        )
        yield _capture_source(
            path,
            title,
            CHATGPT_COVERAGE,
            partial(_chatgpt_records, conversation),
            project=_capture_project(fields),
        )


def _zip_sources(path: Path) -> list[Source]:
    sources = []
    with ZipFile(path) as archive:
        members = [
            member
            for member in archive.infolist()
            if not member.is_dir()
            and _chatgpt_filename(PurePosixPath(member.filename).name)
        ]
        if not members:
            raise ValueError("The ZIP contains no conversations*.json files.")
        for member in members:
            with archive.open(member) as stream:
                try:
                    sources.extend(_chatgpt_sources(json.load(stream), path))
                except (UnicodeError, ValueError) as error:
                    raise ValueError(
                        f"Cannot read {member.filename} in {path.name}: {error}"
                    ) from error
    return sources


def _har_records(document: dict) -> Iterator[Record]:
    log = document["log"]
    metadata = {
        **document,
        "log": {key: value for key, value in log.items() if key != "entries"},
    }
    yield _record("HAR metadata", "Archive metadata", metadata, direction="metadata")

    for entry in log["entries"]:
        fields = _obj(entry)
        request = _obj(fields.get("request"))
        response = _obj(fields.get("response"))
        method = _text(request.get("method"), "HTTP")
        url = request.get("url")
        url = (
            _text(url.split("?", 1)[0].split("#", 1)[0]) if isinstance(url, str) else ""
        )
        status = response.get("status")
        summary = f"{method} {url}".rstrip()
        if isinstance(status, int) and status > 0:
            summary += f" → {status}"
        yield _record(
            "HTTP exchange",
            summary,
            entry,
            _timestamp(fields.get("startedDateTime")),
            "exchange",
        )


def _url_host(value: object) -> str:
    if isinstance(value, str):
        try:
            return short_title(urlsplit(value).hostname)
        except ValueError:
            pass
    return ""


def _har_title(log: dict) -> str:
    pages = log.get("pages")
    if isinstance(pages, list):
        for page in pages:
            title = _obj(page).get("title")
            if isinstance(title, str):
                label = _url_host(title) if "://" in title else short_title(title)
                if label:
                    return label
    for entry in log["entries"]:
        if host := _url_host(_obj(_obj(entry).get("request")).get("url")):
            return f"HTTP capture from {host}"
    return "HTTP capture"


def _json_title(fields: dict) -> str:
    title = short_title(fields.get("title")) or short_title(
        _obj(fields.get("metadata")).get("title")
    )
    if title:
        return title
    model = short_title(fields.get("model"))
    if isinstance(fields.get("model"), str) and (
        "input" in fields or "messages" in fields
    ):
        prompt = fields.get("input")
        title = (
            prompt_title(prompt)
            if isinstance(prompt, str)
            else first_user_title(prompt)
        )
        title = title or first_user_title(fields.get("messages"))
        return title or (f"API request to {model}" if model else "API request")
    if fields.get("object") in ("response", "chat.completion", "chat.completion.chunk"):
        return f"API response from {model}" if model else "API response"
    return "JSON capture"


def _json_item(value: object, fallback: str, direction: str = "") -> Record:
    fields = _obj(value)
    kind = _text(fields.get("type")) or _text(fields.get("object"), "JSON")
    label = _text(fields.get("role")) or _text(fields.get("id"), fallback)
    return _record(kind, label, value, _timestamp(fields.get("created_at")), direction)


def _json_records(document: object) -> Iterator[Record]:
    fields = _obj(document)
    if fields.get("object") == "response" and isinstance(fields.get("output"), list):
        items_key, direction = "output", "received"
    elif fields.get("object") == "list" and isinstance(fields.get("data"), list):
        items_key, direction = "data", ""
    elif isinstance(fields.get("model"), str) and (
        "input" in fields or "messages" in fields
    ):
        yield _record(
            "API request",
            _text(fields["model"], "Model request"),
            document,
            direction="sent",
        )
        return
    else:
        yield _json_item(document, "Imported JSON document")
        return

    metadata = {key: value for key, value in fields.items() if key != items_key}
    yield _record(
        "API metadata",
        "API response metadata",
        metadata,
        _timestamp(fields.get("created_at")),
        "metadata",
    )
    for index, item in enumerate(fields[items_key], 1):
        yield _json_item(item, f"{items_key} item {index}", direction)


def _preview_records(document: dict) -> Iterator[Record]:
    metadata = {key: value for key, value in document.items() if key != "items"}
    yield _record(
        "Preview metadata",
        "Codex prompt preview metadata",
        metadata,
        direction="metadata",
    )
    for index, item in enumerate(document["items"], 1):
        yield _json_item(item, f"Input item {index}", "preview")


def _sse_record(lines: list[str]) -> Record:
    event = ""
    data = []
    for line in lines:
        name, sep, value = line.rstrip("\r\n").partition(":")
        if not sep:
            continue
        value = value.removeprefix(" ")
        if name == "event":
            event = value
        elif name == "data":
            data.append(value)

    payload = "\n".join(data)
    try:
        fields = _obj(json.loads(payload))
    except ValueError:
        fields = {}
    kind = _text(fields.get("type")) or _text(event, "SSE")
    summary = _text(fields.get("delta")) or _text(fields.get("message"))
    summary = summary or _text(payload) or _text(lines[0], "Event stream block")
    return Record(
        kind, summary, "".join(lines), _timestamp(fields.get("created_at")), "received"
    )


def _sse_records(path: Path) -> Iterator[Record]:
    lines = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for line in stream:
            if line.rstrip("\r\n"):
                lines.append(line)
            elif lines:
                yield _sse_record(lines)
                lines = []
    if lines:
        yield _sse_record(lines)


def list_import(path: Path) -> list[Source]:
    """Index a supported file and return sources that yield records on demand."""
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return _zip_sources(path)
    if suffix == ".sse":
        return [
            _capture_source(
                path,
                "Server-sent event stream",
                SSE_COVERAGE,
                partial(_sse_records, path),
            )
        ]
    if suffix not in {".har", ".json"}:
        raise ValueError(
            "Select a ChatGPT export ZIP, JSON file, browser HAR, or SSE stream."
        )

    with path.open("rb") as stream:
        document = json.load(stream)
    fields = _obj(document)
    log = _obj(fields.get("log"))
    if isinstance(log.get("entries"), list):
        return [
            _capture_source(
                path, _har_title(log), HAR_COVERAGE, partial(_har_records, document)
            )
        ]
    if suffix == ".har":
        raise ValueError("The HAR archive has no log.entries array.")
    if fields.get("format") == "codex-prompt-preview" and isinstance(
        fields.get("items"), list
    ):
        title = first_user_title(fields["items"]) or "Codex prompt preview"
        return [
            _capture_source(
                path,
                title,
                PREVIEW_COVERAGE,
                partial(_preview_records, fields),
                project=_capture_project(fields),
            )
        ]
    if _chatgpt_filename(path.name) or isinstance(fields.get("mapping"), dict):
        return list(_chatgpt_sources(document, path))
    if isinstance(document, list) and any(
        isinstance(_obj(item).get("mapping"), dict) for item in document
    ):
        return list(_chatgpt_sources(document, path))
    return [
        _capture_source(
            path,
            _json_title(fields),
            JSON_COVERAGE,
            partial(_json_records, document),
            project=_capture_project(fields),
        )
    ]
