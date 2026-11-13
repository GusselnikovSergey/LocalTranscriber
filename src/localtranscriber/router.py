"""Определение типа входного файла и маршрутизация на движок."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from .errors import UnsupportedFileError


class JobKind(StrEnum):
    SPEECH = "speech"
    IMAGE = "image"
    PDF = "pdf"


SPEECH_EXTS: frozenset[str] = frozenset(
    {
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".ogg",
        ".opus",
        ".flac",
        ".wma",
        ".mp4",
        ".m4v",
        ".mkv",
        ".avi",
        ".mov",
        ".webm",
        ".mpg",
        ".mpeg",
        ".ts",
        ".3gp",
        ".flv",
    }
)
IMAGE_EXTS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
)
PDF_EXTS: frozenset[str] = frozenset({".pdf"})

KIND_LABELS: dict[JobKind, str] = {
    JobKind.SPEECH: "Речь",
    JobKind.IMAGE: "Изображение",
    JobKind.PDF: "PDF",
}


def detect_kind(path: str | Path) -> JobKind:
    """Определяет тип файла по расширению."""
    suffix = Path(path).suffix.lower()
    if suffix in SPEECH_EXTS:
        return JobKind.SPEECH
    if suffix in IMAGE_EXTS:
        return JobKind.IMAGE
    if suffix in PDF_EXTS:
        return JobKind.PDF
    raise UnsupportedFileError(
        f"Формат «{suffix or 'без расширения'}» не поддерживается. "
        "Поддерживаются: " + ", ".join(sorted(supported_extensions()))
    )


def supported_extensions() -> tuple[str, ...]:
    return tuple(sorted(SPEECH_EXTS | IMAGE_EXTS | PDF_EXTS))


def file_dialog_types() -> list[tuple[str, str]]:
    """Список фильтров для диалогов выбора файлов."""
    speech = " ".join(f"*{ext}" for ext in sorted(SPEECH_EXTS))
    images = " ".join(f"*{ext}" for ext in sorted(IMAGE_EXTS))
    return [
        ("Все поддерживаемые", f"{speech} {images} *.pdf"),
        ("Аудио и видео", speech),
        ("Изображения", images),
        ("PDF", "*.pdf"),
        ("Все файлы", "*.*"),
    ]
