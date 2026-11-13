"""Платформенные мелочи: открыть папку, подписи и привязки горячих клавиш."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def is_macos() -> bool:
    return sys.platform == "darwin"


def open_in_file_manager(path: Path) -> None:
    """Открывает каталог в системном файловом менеджере.

    Windows — ``os.startfile``, macOS — ``open``, остальные — ``xdg-open``.
    Ошибку запуска не пробрасываем: это вспомогательное действие, из-за него
    приложение не должно падать (вызывающий код показывает свой диалог).
    """
    target = str(path)
    if sys.platform == "win32":
        os.startfile(target)
        return
    command = "open" if is_macos() else "xdg-open"
    try:
        subprocess.Popen(
            [command, target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return


def modifier_label() -> str:
    """Подпись модификатора для меню: на macOS принято ``Cmd``."""
    return "Cmd" if is_macos() else "Ctrl"


def shortcut_bindings(key: str) -> tuple[str, ...]:
    """Последовательности Tk для действия.

    На macOS основная клавиша — Command, но Control тоже оставляем: так проще
    для тех, кто привык к Windows-раскладке.
    """
    if is_macos():
        return (f"<Command-{key}>", f"<Control-{key}>")
    return (f"<Control-{key}>",)
