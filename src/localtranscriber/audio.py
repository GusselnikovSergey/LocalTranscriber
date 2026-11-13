"""Декодирование аудио и видео в моно 16 кГц без внешнего ffmpeg."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .cancellation import CancelToken
from .errors import AudioDecodeError, CancelledError

_log = logging.getLogger(__name__)
TARGET_RATE = 16_000
ProgressCallback = Callable[[float, str], None]


@dataclass(slots=True)
class DecodedAudio:
    samples: np.ndarray
    duration: float
    sample_rate: int = TARGET_RATE


def probe_duration(path: str | Path) -> float:
    """Длительность медиафайла в секундах; 0.0, если определить не удалось."""
    try:
        import av
    except ImportError:  # pragma: no cover - av обязателен в рабочей сборке
        return 0.0
    try:
        with av.open(str(path)) as container:
            if container.duration:
                return float(container.duration) / 1_000_000
            audio = next((s for s in container.streams if s.type == "audio"), None)
            if audio is not None and audio.duration and audio.time_base:
                return float(audio.duration * audio.time_base)
    except Exception as exc:  # noqa: BLE001 - метаданные не критичны
        _log.debug("Не удалось определить длительность %s: %s", path, exc)
    return 0.0


def decode_audio(
    path: str | Path,
    *,
    cancel: CancelToken | None = None,
    progress: ProgressCallback | None = None,
) -> DecodedAudio:
    """Декодирует первую звуковую дорожку в float32 mono 16 кГц."""
    try:
        import av
    except ImportError as exc:  # pragma: no cover
        raise AudioDecodeError("Библиотека PyAV не установлена") from exc

    total = probe_duration(path)
    chunks: list[np.ndarray] = []
    decoded_seconds = 0.0

    try:
        with av.open(str(path)) as container:
            stream: Any = next(
                (s for s in container.streams if s.type == "audio"), None
            )
            if stream is None:
                raise AudioDecodeError(
                    "В файле нет звуковой дорожки — распознавать нечего. "
                    "Если это видео без звука, транскрибация невозможна."
                )
            stream.thread_type = "AUTO"
            resampler = av.AudioResampler(format="flt", layout="mono", rate=TARGET_RATE)
            for raw_frame in container.decode(stream):
                frame: Any = raw_frame
                if cancel is not None:
                    cancel.raise_if_cancelled()
                for converted in resampler.resample(frame):
                    array = converted.to_ndarray()
                    chunks.append(np.asarray(array, dtype=np.float32).reshape(-1))
                decoded_seconds += float(frame.samples) / float(frame.sample_rate or TARGET_RATE)
                if progress is not None:
                    fraction = min(decoded_seconds / total, 1.0) if total > 0 else 0.0
                    progress(fraction, "Декодирование звука")
            for converted in resampler.resample(None):
                array = converted.to_ndarray()
                chunks.append(np.asarray(array, dtype=np.float32).reshape(-1))
    except CancelledError:
        raise
    except AudioDecodeError:
        raise
    except Exception as exc:  # noqa: BLE001 - любые сбои декодера приводим к доменной ошибке
        _log.exception("Ошибка декодирования %s", path)
        raise AudioDecodeError(f"Не удалось прочитать звук из файла: {exc}") from exc

    if not chunks:
        raise AudioDecodeError("Звуковая дорожка пуста или повреждена")

    samples = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
    duration = float(samples.size) / TARGET_RATE
    if duration <= 0:
        raise AudioDecodeError("Звуковая дорожка пуста или повреждена")
    return DecodedAudio(samples=samples, duration=duration)
