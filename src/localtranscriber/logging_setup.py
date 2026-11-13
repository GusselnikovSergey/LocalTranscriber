"""Логирование в файл с ротацией."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import logs_dir

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_configured = False


def setup_logging(log_dir: Path | None = None, level: int = logging.INFO) -> Path:
    """Настраивает корневой логгер один раз и возвращает путь к файлу лога."""
    global _configured
    directory = log_dir or logs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / "app.log"

    root = logging.getLogger()
    if _configured:
        return log_file

    root.setLevel(level)
    handler = RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    _configured = True
    logging.getLogger(__name__).info("Логирование включено: %s", log_file)
    return log_file


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
