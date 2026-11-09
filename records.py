from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator


@dataclass(frozen=True)
class Record:
    kind: str
    summary: str
    raw: str
    timestamp: str = ""
    direction: str = ""


@dataclass(frozen=True)
class Source:
    title: str
    coverage: str
    load: Callable[[], Iterator[Record]]
    trace_path: Path | None = None
