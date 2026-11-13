from __future__ import annotations

import pytest

from localtranscriber.errors import UnsupportedFileError
from localtranscriber.router import (
    JobKind,
    detect_kind,
    file_dialog_types,
    supported_extensions,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Запись.MP3", JobKind.SPEECH),
        ("video.mp4", JobKind.SPEECH),
        ("audio.flac", JobKind.SPEECH),
        ("scan.png", JobKind.IMAGE),
        ("photo.JPEG", JobKind.IMAGE),
        ("document.pdf", JobKind.PDF),
    ],
)
def test_detect_kind(name: str, expected: JobKind) -> None:
    assert detect_kind(name) is expected


def test_detect_kind_uses_extension_only() -> None:
    assert detect_kind("folder.with.dots/report.pdf") is JobKind.PDF


def test_unsupported_extension() -> None:
    with pytest.raises(UnsupportedFileError) as info:
        detect_kind("notes.docx")
    assert ".docx" in str(info.value)


def test_supported_extensions_include_main_formats() -> None:
    extensions = supported_extensions()
    for ext in (".mp3", ".mp4", ".wav", ".png", ".pdf", ".webp"):
        assert ext in extensions


def test_file_dialog_types_are_tuples() -> None:
    types = file_dialog_types()
    assert types and all(len(item) == 2 for item in types)
    assert types[0][0] == "Все поддерживаемые"
