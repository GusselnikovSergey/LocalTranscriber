"""Сквозная проверка движков на тестовых данных.

Пример: python scripts/make_testdata.py --out testdata/generated
        python scripts/smoke_check.py --data testdata/generated --model small
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from localtranscriber.cancellation import CancelToken
from localtranscriber.engines.ocr_engine import OcrEngine
from localtranscriber.engines.whisper_engine import WhisperEngine
from localtranscriber.models_setup import ensure_whisper_model
from localtranscriber.pdf import extract_pdf

CANCEL = CancelToken()


def no_progress(fraction: float, message: str) -> None:
    _ = (fraction, message)


def check_ocr(data: Path) -> None:
    engine = OcrEngine()
    started = time.perf_counter()
    result = engine.process(data / "sample.png", cancel=CANCEL, progress=no_progress)
    first = time.perf_counter() - started
    started = time.perf_counter()
    engine.process(data / "sample.png", cancel=CANCEL, progress=no_progress)
    warm = time.perf_counter() - started
    print(f"[OCR] первый запуск {first:.1f} с, повторный {warm:.2f} с")
    print(result.text)


def check_pdf(data: Path) -> None:
    engine = OcrEngine()
    started = time.perf_counter()
    digital = extract_pdf(data / "digital.pdf", ocr=engine)
    print(
        f"[PDF digital] {time.perf_counter() - started:.1f} с, "
        f"OCR-страниц={digital.meta['ocr_pages']}\n{digital.text}"
    )
    started = time.perf_counter()
    scanned = extract_pdf(data / "scanned.pdf", ocr=engine)
    print(
        f"[PDF scanned] {time.perf_counter() - started:.1f} с, "
        f"OCR-страниц={scanned.meta['ocr_pages']}\n{scanned.text}"
    )


def check_whisper(data: Path, model_size: str, language: str) -> None:
    sample = data / "speech_en.wav"
    if not sample.exists():
        print(f"[Whisper] нет {sample} — пропуск")
        return
    started = time.perf_counter()
    model_path = ensure_whisper_model(model_size, progress=no_progress)
    print(f"[Whisper] модель {model_size} готова за {time.perf_counter() - started:.1f} с")
    engine = WhisperEngine(
        model_size, cpu_threads=16, language=language, model_path=model_path
    )
    started = time.perf_counter()
    result = engine.process(sample, cancel=CANCEL, progress=no_progress)
    elapsed = time.perf_counter() - started
    rtf = elapsed / max(result.duration, 0.01)
    print(f"[Whisper {model_size}] {elapsed:.1f} с, RTF={rtf:.2f}, мета={result.meta}")
    print(result.text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="testdata/generated")
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="en")
    parser.add_argument("--skip", nargs="*", default=[])
    args = parser.parse_args()

    data = Path(args.data)
    if not data.is_dir():
        print(f"Нет каталога {data}. Сначала выполните scripts/make_testdata.py")
        return 2

    steps = {
        "ocr": lambda: check_ocr(data),
        "pdf": lambda: check_pdf(data),
        "whisper": lambda: check_whisper(data, args.model, args.language),
    }
    for name, step in steps.items():
        if name not in args.skip:
            step()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
