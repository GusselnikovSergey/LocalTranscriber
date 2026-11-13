"""Потокобезопасный флаг отмены задания."""

from __future__ import annotations

import threading

from .errors import CancelledError


class CancelToken:
    """Простая обёртка над ``threading.Event`` с проверкой в движках."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise CancelledError("Задание отменено")
