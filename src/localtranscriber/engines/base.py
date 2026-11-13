"""Общий контракт движков: результат, прогресс, отмена."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..cancellation import CancelToken
from ..textformat import Segment

ProgressCallback = Callable[[float, str], None]


@dataclass(slots=True)
class Result:
    """Результат обработки одного файла."""

    kind: str
    text: str
    segments: list[Segment] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    language: str = ""
    duration: float = 0.0
    meta: dict[str, object] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@runtime_checkable
class Processor(Protocol):
    """Движок, способный превратить файл в текст."""

    name: str

    def process(
        self, path: Path, *, cancel: CancelToken, progress: ProgressCallback
    ) -> Result: ...
