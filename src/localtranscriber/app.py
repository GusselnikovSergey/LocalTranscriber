"""Точка входа приложения."""

from __future__ import annotations

import logging
import tkinter as tk

from . import __version__
from .config import load_settings
from .logging_setup import setup_logging
from .network import ensure_system_trust
from .ui.main_window import MainWindow

_log = logging.getLogger(__name__)


def _enable_dpi_awareness() -> None:
    """Чёткий текст на экранах с масштабированием Windows."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - не критично и не существует вне Windows
        pass


def create_root() -> tk.Tk:
    """Tk-корень с поддержкой drag&drop, если установлен tkinterdnd2."""
    try:
        from tkinterdnd2 import TkinterDnD

        return TkinterDnD.Tk()
    except Exception:  # noqa: BLE001 - drag&drop опционален
        _log.info("tkinterdnd2 недоступен, используется обычный Tk")
        return tk.Tk()


def main(argv: list[str] | None = None) -> int:
    _ = argv
    ensure_system_trust()
    log_file = setup_logging()
    settings = load_settings()
    _enable_dpi_awareness()
    try:
        root = create_root()
    except tk.TclError as exc:
        _log.error("Не удалось создать окно: %s", exc)
        print(f"Не удалось запустить графический интерфейс: {exc}")
        return 1

    root.title(f"LocalTranscriber {__version__} — локальная транскрибация")
    root.geometry("1150x720")
    root.minsize(940, 620)
    _log.info(
        "Старт приложения: модель=%s, язык=%s, потоков=%s, лог=%s",
        settings.model_size,
        settings.language,
        settings.cpu_threads,
        log_file,
    )
    MainWindow(root, settings)
    root.mainloop()
    return 0
