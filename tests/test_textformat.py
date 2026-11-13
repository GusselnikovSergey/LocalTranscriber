from __future__ import annotations

import json

import pytest

from localtranscriber.textformat import (
    Segment,
    export_text,
    format_short_timestamp,
    format_timestamp,
    normalize_text,
    pages_to_text,
    safe_filename,
    segments_to_cues,
    segments_to_json,
    segments_to_srt,
    segments_to_text,
    segments_to_vtt,
)

SEGMENTS = [
    Segment(0.0, 2.5, " Привет, это тест. "),
    Segment(2.6, 4.0, "Вторая фраза."),
    Segment(8.0, 9.5, "Новый абзац."),
]


def test_timestamp_formats() -> None:
    assert format_timestamp(0) == "00:00:00,000"
    assert format_timestamp(61.25) == "00:01:01,250"
    assert format_timestamp(3661.5, decimal_sep=".") == "01:01:01.500"
    assert format_short_timestamp(75) == "01:15"
    assert format_short_timestamp(3725) == "1:02:05"


def test_normalize_text() -> None:
    assert normalize_text("  a\t\tb\nc  ") == "a b c"


def test_segments_to_text_breaks_on_pause() -> None:
    text = segments_to_text(SEGMENTS, gap=1.0)
    assert text == "Привет, это тест. Вторая фраза.\n\nНовый абзац."


def test_segments_to_text_ignores_empty() -> None:
    assert segments_to_text([Segment(0, 1, "   ")]) == ""


def test_segments_to_cues() -> None:
    cues = segments_to_cues(SEGMENTS)
    assert cues.splitlines()[0] == "[00:00] Привет, это тест."


def test_srt_structure() -> None:
    content = segments_to_srt(SEGMENTS)
    blocks = content.strip().split("\n\n")
    assert len(blocks) == 3
    assert blocks[0].splitlines()[0] == "1"
    assert blocks[0].splitlines()[1] == "00:00:00,000 --> 00:00:02,500"
    assert content.endswith("\n")


def test_vtt_structure() -> None:
    content = segments_to_vtt(SEGMENTS)
    assert content.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.500" in content


def test_json_structure() -> None:
    payload = json.loads(segments_to_json(SEGMENTS, meta={"model": "small"}))
    assert payload["meta"]["model"] == "small"
    assert len(payload["segments"]) == 3
    assert payload["segments"][0]["start"] == 0.0
    assert payload["segments"][0]["text"] == "Привет, это тест."


def test_pages_markers() -> None:
    text = pages_to_text(["Первая", "", "Третья"])
    assert "--- стр. 1 ---" in text
    assert "--- стр. 3 ---" in text
    assert "--- стр. 2 ---" not in text


def test_single_page_without_markers() -> None:
    assert pages_to_text(["Только текст"]) == "Только текст"
    assert pages_to_text([]) == ""


def test_safe_filename() -> None:
    assert safe_filename('отчет: "тест"/2026') == "отчет_ _тест__2026"
    assert safe_filename("   ") == "result"


def test_export_text_formats() -> None:
    assert export_text("txt", "привет") == "привет\n"
    assert export_text("srt", "привет", segments=SEGMENTS).startswith("1\n")
    assert export_text("vtt", "", segments=SEGMENTS).startswith("WEBVTT")
    assert "segments" in export_text("json", "", segments=SEGMENTS)
    with pytest.raises(ValueError):
        export_text("docx", "текст")
