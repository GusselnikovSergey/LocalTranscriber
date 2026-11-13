"""Распознавание речи локально: faster-whisper на CPU (int8)."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from ..audio import decode_audio
from ..cancellation import CancelToken
from ..config import models_dir
from ..textformat import Segment, segments_to_text
from .base import ProgressCallback, Result

_log = logging.getLogger(__name__)

MODEL_REPOS: dict[str, str] = {
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}

DECODE_SHARE = 0.15  # доля прогресса, отведённая декодированию звука
CANCEL_POLL = 0.1  # как часто проверять отмену, пока модель считает сегмент


def iter_with_cancel(
    raw_segments: Iterable[Any], cancel: CancelToken
) -> Iterator[Any]:
    """Отдаёт сегменты, не блокируя проверку отмены.

    ``faster_whisper`` не умеет прерывать генерацию: первый сегмент на длинной
    записи может считаться несколько секунд, и проверка токена между сегментами
    не успевает сработать (FR-05 требует ≤3 с). Поэтому сегменты вытягивает
    отдельный поток, а основной ждёт их с коротким таймаутом и реагирует на
    отмену сразу. Незавершённый сегмент досчитывается в фоне и выбрасывается.
    """
    events: queue.Queue[tuple[str, Any]] = queue.Queue()
    stop = threading.Event()

    def pump() -> None:
        try:
            for item in raw_segments:
                events.put(("segment", item))
                if stop.is_set():
                    break
        except BaseException as exc:  # noqa: BLE001 - пробрасываем в основной поток
            events.put(("error", exc))
        finally:
            events.put(("end", None))

    thread = threading.Thread(target=pump, name="whisper-segments", daemon=True)
    thread.start()
    try:
        while True:
            cancel.raise_if_cancelled()
            try:
                kind, payload = events.get(timeout=CANCEL_POLL)
            except queue.Empty:
                continue
            if kind == "segment":
                yield payload
            elif kind == "error":
                raise payload
            else:
                return
    finally:
        # Просим поток остановиться после текущего сегмента; ждать его нельзя —
        # именно это ожидание и нарушало требование по времени отмены.
        stop.set()


def model_directory(size: str, root: Path | None = None) -> Path:
    """Каталог локальной копии модели (наш формат хранения)."""
    base = root or models_dir()
    return base / f"whisper-{size}"


def collect_segments(
    raw_segments: Iterable[Any],
    *,
    duration: float,
    cancel: CancelToken,
    progress: ProgressCallback,
    start_share: float = DECODE_SHARE,
) -> list[Segment]:
    """Преобразует сегменты faster-whisper в наши, обновляя прогресс и проверяя отмену."""
    collected: list[Segment] = []
    span = max(0.0, 1.0 - start_share)
    for raw in raw_segments:
        cancel.raise_if_cancelled()
        text = str(getattr(raw, "text", "") or "").strip()
        if not text:
            continue
        segment = Segment(
            start=float(getattr(raw, "start", 0.0) or 0.0),
            end=float(getattr(raw, "end", 0.0) or 0.0),
            text=text,
        )
        collected.append(segment)
        if duration > 0:
            fraction = min(segment.end / duration, 1.0)
            progress(start_share + span * fraction, "Распознавание речи")
    cancel.raise_if_cancelled()
    progress(1.0, "Готово")
    return collected


class WhisperEngine:
    """Ленивая обёртка над ``faster_whisper.WhisperModel``."""

    name = "faster-whisper"

    def __init__(
        self,
        model_size: str = "medium",
        *,
        cpu_threads: int | None = None,
        language: str = "ru",
        model_path: Path | None = None,
        compute_type: str = "int8",
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.model_size = model_size
        self.cpu_threads = cpu_threads
        self.language = language
        self.model_path = model_path
        self.compute_type = compute_type
        self._model: Any | None = None
        self._model_factory = model_factory

    @property
    def display_name(self) -> str:
        return f"Whisper {self.model_size}"

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self._model_factory is not None:
            self._model = self._model_factory()
            return self._model

        from faster_whisper import WhisperModel

        target = str(self.model_path) if self.model_path else self.model_size
        kwargs: dict[str, Any] = {
            "device": "cpu",
            "compute_type": self.compute_type,
        }
        if self.cpu_threads:
            kwargs["cpu_threads"] = int(self.cpu_threads)
        if self.model_path is None:
            kwargs["download_root"] = str(models_dir())
        started = time.perf_counter()
        model = WhisperModel(target, **kwargs)
        _log.info(
            "Модель %s загружена за %.1f с (threads=%s)",
            self.model_size,
            time.perf_counter() - started,
            self.cpu_threads,
        )
        self._model = model
        return model

    def process(
        self, path: Path, *, cancel: CancelToken, progress: ProgressCallback
    ) -> Result:
        decoded = decode_audio(
            path, cancel=cancel, progress=lambda fraction, message: progress(
                fraction * DECODE_SHARE, message
            )
        )
        progress(DECODE_SHARE, "Подготовка модели")
        model = self._load_model()
        cancel.raise_if_cancelled()
        progress(DECODE_SHARE, "Распознавание речи")

        language = None if self.language in ("", "auto") else self.language
        started = time.perf_counter()
        raw_segments, info = model.transcribe(
            decoded.samples,
            language=language,
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 200},
            condition_on_previous_text=False,
            word_timestamps=False,
        )
        segments = collect_segments(
            iter_with_cancel(raw_segments, cancel),
            duration=decoded.duration,
            cancel=cancel,
            progress=progress,
        )
        elapsed = time.perf_counter() - started
        text = segments_to_text(segments)
        detected = str(getattr(info, "language", "") or language or "")
        _log.info(
            "Распознан %s: %.1f с звука за %.1f с (%.2f×RT), сегментов=%d",
            Path(path).name,
            decoded.duration,
            elapsed,
            decoded.duration / elapsed if elapsed else 0.0,
            len(segments),
        )
        return Result(
            kind="speech",
            text=text,
            segments=segments,
            language=detected,
            duration=decoded.duration,
            meta={
                "engine": self.name,
                "model": self.model_size,
                "elapsed": round(elapsed, 2),
                "realtime_factor": round(decoded.duration / elapsed, 2) if elapsed else 0.0,
            },
        )
