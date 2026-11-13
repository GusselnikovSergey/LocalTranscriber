"""Форматирование результата: абзацы, таймкоды, экспорт txt/srt/vtt/json."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

PARAGRAPH_GAP_SECONDS = 1.0
SPACE_RE = re.compile(r"[ \t\u00a0]+")
INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(slots=True)
class Segment:
    """Распознанный фрагмент речи с границами во времени."""

    start: float
    end: float
    text: str


def normalize_text(text: str) -> str:
    """Убирает лишние пробелы и служебные символы по краям."""
    cleaned = SPACE_RE.sub(" ", str(text).replace("\r", " ").replace("\n", " ")).strip()
    return cleaned


def format_timestamp(seconds: float, *, decimal_sep: str = ",") -> str:
    """00:00:01,250 для SRT или 00:00:01.250 для VTT."""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal_sep}{millis:03d}"


def format_short_timestamp(seconds: float) -> str:
    """Компактный вид для редактора: 01:23 или 1:02:03."""
    total = max(0, int(round(float(seconds))))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def segments_to_text(
    segments: Iterable[Segment], *, gap: float = PARAGRAPH_GAP_SECONDS
) -> str:
    """Склеивает сегменты в абзацы, разрывая их на паузах длиннее ``gap``."""
    paragraphs: list[str] = []
    current: list[str] = []
    last_end: float | None = None
    for segment in segments:
        text = normalize_text(segment.text)
        if not text:
            continue
        if last_end is not None and segment.start - last_end >= gap and current:
            paragraphs.append(" ".join(current))
            current = []
        current.append(text)
        last_end = max(last_end or 0.0, segment.end)
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def segments_to_cues(segments: Iterable[Segment], *, with_timestamps: bool = True) -> str:
    """Построчный вид: [00:12] текст — для просмотра с таймкодами."""
    lines: list[str] = []
    for segment in segments:
        text = normalize_text(segment.text)
        if not text:
            continue
        if with_timestamps:
            lines.append(f"[{format_short_timestamp(segment.start)}] {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def segments_to_srt(segments: Iterable[Segment]) -> str:
    """Формат SubRip."""
    blocks: list[str] = []
    index = 0
    for segment in segments:
        text = normalize_text(segment.text)
        if not text:
            continue
        index += 1
        start = format_timestamp(segment.start)
        end = format_timestamp(max(segment.end, segment.start + 0.05))
        blocks.append(f"{index}\n{start} --> {end}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def segments_to_vtt(segments: Iterable[Segment]) -> str:
    """Формат WebVTT."""
    blocks: list[str] = ["WEBVTT", ""]
    for segment in segments:
        text = normalize_text(segment.text)
        if not text:
            continue
        start = format_timestamp(segment.start, decimal_sep=".")
        end = format_timestamp(max(segment.end, segment.start + 0.05), decimal_sep=".")
        blocks.append(f"{start} --> {end}\n{text}")
        blocks.append("")
    return "\n".join(blocks).rstrip("\n") + "\n"


def segments_to_json(segments: Iterable[Segment], *, meta: dict | None = None) -> str:
    """Машиночитаемый результат с таймкодами."""
    payload = {
        "meta": meta or {},
        "segments": [
            {
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "text": normalize_text(segment.text),
            }
            for segment in segments
            if normalize_text(segment.text)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def pages_to_text(pages: Sequence[str], *, mark_pages: bool = True) -> str:
    """Склеивает страницы PDF, помечая их номерами при необходимости."""
    cleaned = [page.strip() for page in pages]
    non_empty = [page for page in cleaned if page]
    if not non_empty:
        return ""
    if not mark_pages or len(cleaned) == 1:
        return "\n\n".join(non_empty)
    parts: list[str] = []
    for number, page in enumerate(cleaned, start=1):
        if not page:
            continue
        parts.append(f"--- стр. {number} ---\n{page}")
    return "\n\n".join(parts)


def safe_filename(name: str, *, fallback: str = "result") -> str:
    """Имя файла без запрещённых в Windows символов."""
    cleaned = INVALID_FILENAME_RE.sub("_", str(name)).strip(" .")
    return cleaned or fallback


def export_text(
    fmt: str,
    text: str,
    *,
    segments: Sequence[Segment] = (),
    meta: dict | None = None,
) -> str:
    """Содержимое файла для выбранного формата.

    ``txt`` использует отредактированный пользователем текст, форматы с таймкодами —
    исходные сегменты (правки в редакторе на них не влияют).
    """
    key = fmt.lower().lstrip(".")
    if key in ("txt", "text"):
        return text if text.endswith("\n") else text + "\n"
    if key == "srt":
        return segments_to_srt(segments)
    if key == "vtt":
        return segments_to_vtt(segments)
    if key == "json":
        return segments_to_json(segments, meta=meta)
    raise ValueError(f"Неизвестный формат экспорта: {fmt}")
