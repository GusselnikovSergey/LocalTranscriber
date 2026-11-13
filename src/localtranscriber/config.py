"""Настройки приложения и стандартные пути для Windows, macOS и Linux."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

APP_NAME = "LocalTranscriber"

MODEL_SIZES: tuple[str, ...] = ("small", "medium", "large-v3")
DEFAULT_MODEL = "medium"

LANGUAGES: dict[str, str] = {
    "ru": "Русский",
    "auto": "Автоопределение",
    "en": "Английский",
}
DEFAULT_LANGUAGE = "ru"
OCR_LANGUAGES: tuple[str, ...] = ("cyrillic", "latin", "ch")

_log = logging.getLogger(__name__)


def _as_bool(value: Any) -> bool:
    """Превращает значение из JSON в bool: строка ``"false"`` не должна стать True."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "да"}
    return bool(value)


def _env_dir(variable: str, fallback: Path) -> Path:
    value = os.environ.get(variable)
    return Path(value) if value else fallback


def _is_macos() -> bool:
    return sys.platform == "darwin"


def appdata_dir() -> Path:
    """Каталог настроек.

    Windows: ``%APPDATA%\\LocalTranscriber``;
    macOS: ``~/Library/Application Support/LocalTranscriber``.
    """
    if _is_macos():
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return _env_dir("APPDATA", Path.home() / "AppData" / "Roaming") / APP_NAME


def localappdata_dir() -> Path:
    """Каталог данных (модели, кэш).

    Windows: ``%LOCALAPPDATA%\\LocalTranscriber``;
    macOS: ``~/Library/Application Support/LocalTranscriber``.
    """
    if _is_macos():
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return _env_dir("LOCALAPPDATA", Path.home() / "AppData" / "Local") / APP_NAME


def models_dir() -> Path:
    return localappdata_dir() / "models"


def logs_dir() -> Path:
    """Каталог логов: на macOS принято держать их отдельно от данных."""
    if _is_macos():
        return Path.home() / "Library" / "Logs" / APP_NAME
    return localappdata_dir() / "logs"


def settings_path() -> Path:
    return appdata_dir() / "settings.json"


def default_output_dir() -> Path:
    return Path.home() / "Documents" / APP_NAME


def default_cpu_threads() -> int:
    """Половина логических ядер, но не больше 16.

    Замеры на 2 × Xeon E5-2696 v3 (72 потока): 8–18 потоков дают одинаковую
    скорость (≈6× реального времени для ``small``), а 36 потоков — вдвое
    медленнее из-за конкуренции за кэш. Поэтому по умолчанию на серверных
    машинах берём 16, а не половину всех потоков.
    """
    cpu = os.cpu_count() or 4
    return max(1, min(16, cpu // 2))


@dataclass(slots=True)
class Settings:
    """Пользовательские настройки, сохраняемые между запусками."""

    model_size: str = DEFAULT_MODEL
    language: str = DEFAULT_LANGUAGE
    cpu_threads: int = field(default_factory=default_cpu_threads)
    output_dir: str = field(default_factory=lambda: str(default_output_dir()))
    show_timestamps: bool = False
    ocr_lang: str = "cyrillic"

    def normalized(self) -> Settings:
        """Приводит значения к допустимым, не падая на повреждённых данных."""
        size = str(self.model_size).strip()
        if size not in MODEL_SIZES:
            size = DEFAULT_MODEL
        language = str(self.language).strip()
        if language not in LANGUAGES:
            language = DEFAULT_LANGUAGE
        max_threads = max(1, (os.cpu_count() or 4) * 2)
        try:
            threads = int(self.cpu_threads)
        except (TypeError, ValueError):
            threads = default_cpu_threads()
        threads = max(1, min(threads, max_threads))
        output = str(self.output_dir).strip() or str(default_output_dir())
        ocr_lang = str(self.ocr_lang or "cyrillic").strip().lower()
        if ocr_lang not in OCR_LANGUAGES:
            ocr_lang = "cyrillic"
        return Settings(
            model_size=size,
            language=language,
            cpu_threads=threads,
            output_dir=output,
            show_timestamps=_as_bool(self.show_timestamps),
            ocr_lang=ocr_lang,
        )

    def to_dict(self) -> dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    def resolved_output_dir(self) -> Path:
        path = Path(os.path.expandvars(os.path.expanduser(self.output_dir)))
        if not path.is_absolute():
            # Относительный путь из испорченного settings.json не должен уводить
            # результаты в текущий каталог процесса (R-17).
            path = default_output_dir() / path
        return path


def load_settings(path: Path | None = None) -> Settings:
    """Читает настройки; при любой проблеме возвращает значения по умолчанию."""
    target = path or settings_path()
    if not target.exists():
        return Settings()
    try:
        raw = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("Не удалось прочитать настройки %s: %s", target, exc)
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    known = {item.name for item in fields(Settings)}
    filtered = {k: v for k, v in raw.items() if k in known}
    try:
        return Settings(**filtered).normalized()
    except TypeError as exc:
        _log.warning("Некорректные настройки %s: %s", target, exc)
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    """Атомарно сохраняет настройки, создавая каталог при необходимости."""
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(settings.normalized().to_dict(), ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(prefix="settings-", suffix=".json", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        os.replace(tmp_name, target)
    except OSError:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return target


def ensure_output_dir(settings: Settings) -> Path:
    """Создаёт папку результатов и возвращает её."""
    path = settings.resolved_output_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
