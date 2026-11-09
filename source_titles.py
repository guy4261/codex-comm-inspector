"""Format compact source labels from saved titles and workspace metadata."""

from pathlib import Path, PurePosixPath, PureWindowsPath


def short_title(value, limit=80):
    if not isinstance(value, str):
        return ""
    text = (
        " ".join(value.split())
        .encode("utf-8", errors="backslashreplace")
        .decode("utf-8")
    )
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def prompt_title(content):
    parts = content if isinstance(content, list) else [content]
    for part in parts:
        value = part.get("text") if isinstance(part, dict) else part
        if not isinstance(value, str) or value.lstrip().startswith(
            (
                "<environment_context>",
                "# AGENTS.md instructions",
                "<external_codex_apps_",
            )
        ):
            continue
        if title := short_title(value):
            return title
    return ""


def first_user_title(items):
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("role") == "user":
                if title := prompt_title(item.get("content")):
                    return title
    return ""


def project_name(workspace):
    if not isinstance(workspace, str) or not workspace.strip():
        return ""
    windows = PureWindowsPath(workspace)
    path_type = PureWindowsPath if windows.drive or "\\" in workspace else PurePosixPath
    path = path_type(workspace)
    if path in (path_type(Path.home()), path_type("~"), path_type("..")):
        return ""
    if (
        path.is_absolute()
        and len(path.parts) == 3
        and path.parts[1].casefold() in {"home", "users"}
    ):
        return ""
    return short_title(path.name, limit=40)


def source_title(title, *, project="", reference=""):
    return " · ".join(part for part in (project, title, reference) if part)
