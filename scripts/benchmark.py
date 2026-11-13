"""Замер скорости распознавания речи: RTF = время обработки / длительность записи.

Пример:
    python scripts/benchmark.py "D:\\audio\\meeting.mp3" --models small medium large-v3
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from localtranscriber.audio import probe_duration
from localtranscriber.cancellation import CancelToken
from localtranscriber.engines.whisper_engine import WhisperEngine
from localtranscriber.models_setup import ensure_whisper_model, whisper_model_path


def run(model_size: str, path: Path, threads: int, language: str) -> None:
    model_path = whisper_model_path(model_size)
    if model_path is None:
        print(f"[{model_size}] модели нет, скачиваю…")
        started = time.perf_counter()

        def progress(fraction: float, message: str) -> None:
            if int(fraction * 100) % 10 == 0:
                print(f"\r  {message}", end="", flush=True)

        model_path = ensure_whisper_model(model_size, progress=progress)
        print(f"\r  загрузка заняла {time.perf_counter() - started:.1f} с")

    engine = WhisperEngine(model_size, cpu_threads=threads, language=language, model_path=model_path)
    started = time.perf_counter()
    result = engine.process(path, cancel=CancelToken(), progress=lambda *_: None)
    elapsed = time.perf_counter() - started
    duration = result.duration or 1.0
    print(
        f"[{model_size}] звук {duration:.1f} с, обработка {elapsed:.1f} с, "
        f"RTF={elapsed / duration:.2f} (быстрее реального времени в {duration / elapsed:.2f}×), "
        f"сегментов={len(result.segments)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="аудио- или видеофайл")
    parser.add_argument("--models", nargs="+", default=["medium"])
    parser.add_argument("--threads", type=int, default=0, help="0 = авто (половина ядер)")
    parser.add_argument("--language", default="ru")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(f"Файл не найден: {path}")
        return 2
    duration = probe_duration(path)
    print(f"Файл: {path.name}, длительность: {duration:.1f} с")
    for model in args.models:
        run(model, path, args.threads, args.language)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
