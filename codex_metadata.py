"""Read the names and workspace information saved by Codex."""

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from source_titles import project_name, prompt_title, short_title


@dataclass(frozen=True)
class ThreadLabel:
    title: str = ""
    project: str = ""


STATE_DATABASE = re.compile(r"state_(\d+)\.sqlite")
DESKTOP_STATE_LIMIT = 8 * 1024 * 1024


def _index_titles(home):
    titles = {}
    try:
        with (home / "session_index.jsonl").open(
            encoding="utf-8-sig", errors="replace"
        ) as index:
            for line in index:
                try:
                    entry = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                    title = short_title(entry.get("thread_name"))
                    if title:
                        titles[entry["id"].lower()] = title
    except OSError:
        pass
    return titles


def _desktop_projects(home):
    try:
        with (home / ".codex-global-state.json").open("rb") as stream:
            raw = stream.read(DESKTOP_STATE_LIMIT + 1)
        if len(raw) > DESKTOP_STATE_LIMIT:
            return {}, {}
        state = json.loads(raw)
    except (OSError, ValueError, RecursionError):
        return {}, {}
    if not isinstance(state, dict):
        return {}, {}

    names = {}
    projects = state.get("local-projects")
    assignments = state.get("thread-project-assignments")
    if isinstance(projects, dict) and isinstance(assignments, dict):
        for thread_id, assignment in assignments.items():
            if (
                not isinstance(assignment, dict)
                or assignment.get("projectKind") != "local"
            ):
                continue
            project_id = assignment.get("projectId")
            project = projects.get(project_id) if isinstance(project_id, str) else None
            if isinstance(project, dict) and (name := short_title(project.get("name"))):
                names[thread_id.lower()] = name

    roots = state.get("thread-workspace-root-hints")
    hints = {}
    if isinstance(roots, dict):
        hints = {
            thread_id.lower(): root
            for thread_id, root in roots.items()
            if isinstance(root, str) and root.strip()
        }
    return names, hints


def _database_threads(home):
    candidates = []
    for path in home.glob("state_*.sqlite"):
        if match := STATE_DATABASE.fullmatch(path.name):
            candidates.append((int(match[1]), path))
    for _, path in sorted(candidates, reverse=True):
        try:
            uri = path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=0.2)) as db:
                threads = {row[1] for row in db.execute("PRAGMA table_info(threads)")}
                if "id" not in threads:
                    continue
                projects = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
                use_projects = "project_id" in threads and {"id", "name"} <= projects
                join = (
                    " LEFT JOIN projects ON projects.id = threads.project_id"
                    if use_projects
                    else ""
                )
                title_fields = [
                    f"substr(threads.{name}, 1, 512)" if name in threads else "NULL"
                    for name in ("name", "title", "first_user_message")
                ]
                fields = [
                    "threads.id",
                    *title_fields,
                    "threads.cwd" if "cwd" in threads else "NULL",
                    "projects.name" if use_projects else "NULL",
                ]
                query = f"SELECT {', '.join(fields)} FROM threads{join}"
                return {
                    thread_id.lower(): (
                        short_title(name)
                        or prompt_title(title)
                        or prompt_title(first_message),
                        cwd or "",
                        short_title(project),
                    )
                    for thread_id, name, title, first_message, cwd, project in db.execute(
                        query
                    )
                    if isinstance(thread_id, str)
                }
        except (OSError, sqlite3.Error):
            continue
    return {}


def read_thread_labels(home: Path) -> dict[str, ThreadLabel]:
    """Collect thread titles and projects without opening rollout files."""
    indexed = _index_titles(home)
    desktop_projects, workspace_hints = _desktop_projects(home)
    database = _database_threads(home)
    labels = {}
    for thread_id in (
        indexed.keys()
        | desktop_projects.keys()
        | workspace_hints.keys()
        | database.keys()
    ):
        title, cwd, project = database.get(thread_id, ("", "", ""))
        labels[thread_id] = ThreadLabel(
            indexed.get(thread_id) or title,
            desktop_projects.get(thread_id)
            or project
            or project_name(workspace_hints.get(thread_id))
            or project_name(cwd),
        )
    return labels
