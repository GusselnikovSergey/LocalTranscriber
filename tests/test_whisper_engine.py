from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from localtranscriber.audio import DecodedAudio, probe_duration
from localtranscriber.cancellation import CancelToken
from localtranscriber.engines.base import Result
from localtranscriber.engines.whisper_engine import (
    WhisperEngine,
    call_with_cancel,
    collect_segments,
    iter_with_cancel,
    model_directory,
)
from localtranscriber.errors import AudioDecodeError, CancelledError


def raw(start: float, end: float, text: str) -> SimpleNamespace:
    return SimpleNamespace(start=start, end=end, text=text)


def test_collect_segments_builds_text_and_progress() -> None:
    progress: list[float] = []
    segments = collect_segments(
        [raw(0, 2, " Привет "), raw(2, 4, "мир")],
        duration=4.0,
        cancel=CancelToken(),
        progress=lambda fraction, _message: progress.append(fraction),
    )
    assert [segment.text for segment in segments] == ["Привет", "мир"]
    assert progress[-1] == 1.0
    assert all(0.0 <= value <= 1.0 for value in progress)
    assert progress[0] < progress[1]


def test_collect_segments_skips_empty() -> None:
    segments = collect_segments(
        [raw(0, 1, "  "), raw(1, 2, "текст")],
        duration=2.0,
        cancel=CancelToken(),
        progress=lambda *_: None,
    )
    assert len(segments) == 1


def test_collect_segments_checks_cancel() -> None:
    cancel = CancelToken()
    cancel.cancel()
    with pytest.raises(CancelledError):
        collect_segments([raw(0, 1, "текст")], duration=1.0, cancel=cancel, progress=lambda *_: None)


def test_iter_with_cancel_passes_segments() -> None:
    assert list(iter_with_cancel([raw(0, 1, "a"), raw(1, 2, "b")], CancelToken()))[1].text == "b"


def test_iter_with_cancel_does_not_wait_for_slow_segment() -> None:
    """Отмена не должна ждать, пока модель досчитает текущий сегмент (FR-05)."""

    def slow():
        time.sleep(2.0)
        yield raw(0, 1, "поздно")

    cancel = CancelToken()
    timer = threading.Timer(0.1, cancel.cancel)
    started = time.perf_counter()
    timer.start()
    try:
        with pytest.raises(CancelledError):
            list(iter_with_cancel(slow(), cancel))
    finally:
        timer.cancel()
    assert time.perf_counter() - started < 1.0


def test_iter_with_cancel_propagates_engine_error() -> None:
    def broken():
        if True:
            raise ValueError("boom")
        yield raw(0, 1, "не дошли")

    with pytest.raises(ValueError, match="boom"):
        list(iter_with_cancel(broken(), CancelToken()))


def test_call_with_cancel_returns_value() -> None:
    assert call_with_cancel(lambda: 42, CancelToken()) == 42


def test_call_with_cancel_propagates_error() -> None:
    def boom() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        call_with_cancel(boom, CancelToken())


def test_call_with_cancel_stops_waiting_for_slow_call() -> None:
    """Отмена не должна ждать, пока подготовка распознавания закончится (D-03)."""
    cancel = CancelToken()
    timer = threading.Timer(0.1, cancel.cancel)
    started = time.perf_counter()
    timer.start()
    try:
        with pytest.raises(CancelledError):
            call_with_cancel(lambda: time.sleep(3.0), cancel)
    finally:
        timer.cancel()
    assert time.perf_counter() - started < 1.0


class FakeModel:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        return (
            iter([raw(0, 1.5, " Проверка распознавания."), raw(1.5, 3.0, "Вторая фраза.")]),
            SimpleNamespace(language="ru"),
        )


def test_process_uses_decoded_audio(monkeypatch, tmp_path) -> None:
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_bytes(b"")

    fake_audio = DecodedAudio(samples=np.zeros(16000, dtype=np.float32), duration=3.0)
    monkeypatch.setattr(
        "localtranscriber.engines.whisper_engine.decode_audio",
        lambda path, cancel=None, progress=None: fake_audio,
    )

    model = FakeModel()
    engine = WhisperEngine("medium", model_factory=lambda: model)
    result = engine.process(audio_path, cancel=CancelToken(), progress=lambda *_: None)
    assert isinstance(result, Result)
    assert "Проверка распознавания. Вторая фраза." in result.text
    assert result.language == "ru"
    assert result.duration == 3.0
    assert model.calls[0]["language"] == "ru"
    assert model.calls[0]["vad_filter"] is True


def test_process_auto_language(monkeypatch, tmp_path) -> None:
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_bytes(b"")
    fake_audio = DecodedAudio(samples=np.zeros(16000, dtype=np.float32), duration=2.0)
    monkeypatch.setattr(
        "localtranscriber.engines.whisper_engine.decode_audio",
        lambda path, cancel=None, progress=None: fake_audio,
    )
    model = FakeModel()
    engine = WhisperEngine("small", language="auto", model_factory=lambda: model)
    engine.process(audio_path, cancel=CancelToken(), progress=lambda *_: None)
    assert model.calls[0]["language"] is None


def test_process_cancel_while_transcribe_call_is_slow(monkeypatch, tmp_path) -> None:
    """Отмена при подготовке распознавания укладывается в FR-05 (D-03).

    ``WhisperModel.transcribe()`` до возврата генератора выполняет VAD и подготовку
    признаков; при отмене в этот момент движок не должен ждать её окончания.
    """
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_bytes(b"")
    fake_audio = DecodedAudio(samples=np.zeros(16000, dtype=np.float32), duration=3.0)
    monkeypatch.setattr(
        "localtranscriber.engines.whisper_engine.decode_audio",
        lambda path, cancel=None, progress=None: fake_audio,
    )

    class SlowCallModel:
        def transcribe(self, audio, **kwargs):
            time.sleep(2.0)
            return iter([raw(0, 1, "поздно")]), SimpleNamespace(language="ru")

    cancel = CancelToken()
    timer = threading.Timer(0.1, cancel.cancel)
    started = time.perf_counter()
    timer.start()
    try:
        with pytest.raises(CancelledError):
            WhisperEngine("small", model_factory=SlowCallModel).process(
                audio_path, cancel=cancel, progress=lambda *_: None
            )
    finally:
        timer.cancel()
    assert time.perf_counter() - started < 1.0


def test_process_cancel_during_model_load(monkeypatch, tmp_path) -> None:
    """Загрузка модели не блокирует отмену: она идёт в фоне и переиспользуется."""
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_bytes(b"")
    fake_audio = DecodedAudio(samples=np.zeros(16000, dtype=np.float32), duration=2.0)
    monkeypatch.setattr(
        "localtranscriber.engines.whisper_engine.decode_audio",
        lambda path, cancel=None, progress=None: fake_audio,
    )
    calls = {"count": 0}

    def slow_factory() -> FakeModel:
        calls["count"] += 1
        time.sleep(1.5)
        return FakeModel()

    engine = WhisperEngine("small", model_factory=slow_factory)
    cancel = CancelToken()
    timer = threading.Timer(0.1, cancel.cancel)
    started = time.perf_counter()
    timer.start()
    try:
        with pytest.raises(CancelledError):
            engine.process(audio_path, cancel=cancel, progress=lambda *_: None)
    finally:
        timer.cancel()
    assert time.perf_counter() - started < 1.0

    # Брошенная загрузка доводится до конца, повторная не запускается.
    assert engine._load_event.wait(5.0)
    assert calls["count"] == 1
    result = engine.process(audio_path, cancel=CancelToken(), progress=lambda *_: None)
    assert result.text
    assert calls["count"] == 1


def test_model_directory_layout(tmp_path) -> None:
    assert model_directory("medium", tmp_path) == tmp_path / "whisper-medium"


def test_probe_duration_on_missing_file(tmp_path) -> None:
    assert probe_duration(tmp_path / "nope.mp3") == 0.0


def test_decode_missing_file_raises(tmp_path) -> None:
    from localtranscriber.audio import decode_audio

    with pytest.raises(AudioDecodeError):
        decode_audio(tmp_path / "nope.mp3")


@pytest.mark.slow
def test_real_speech_recognition(tmp_path) -> None:
    """Распознавание синтетического тона: проверяет сквозной путь движка."""
    if not os.environ.get("RUN_SLOW"):
        pytest.skip("RUN_SLOW не задан")
    import wave

    from localtranscriber.engines.whisper_engine import WhisperEngine as Engine
    from localtranscriber.models_setup import whisper_model_path

    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        frames = np.zeros(16000 * 2, dtype=np.int16).tobytes()
        handle.writeframes(frames)

    engine = Engine("small", cpu_threads=2, model_path=whisper_model_path("small"))
    result = engine.process(path, cancel=CancelToken(), progress=lambda *_: None)
    assert result.duration > 0
