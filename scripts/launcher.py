"""Точка входа для сборки standalone-приложения (PyInstaller).

Запускает то же приложение, что ``python -m localtranscriber``; при сбое до
создания окна пишет сообщение в файл лога и показывает окно с ошибкой.

Диагностика сборки: ``LocalTranscriber.exe --selftest отчёт.json файл1 файл2 …``
прогоняет указанные файлы теми же движками и пишет JSON-отчёт (используется при
сборке, чтобы проверить, что библиотеки распознавания попали в пакет).
"""

from __future__ import annotations

import json
import multiprocessing
import sys
import time
import traceback
from pathlib import Path

from localtranscriber.app import main


def run_selftest(paths: list[str], out: Path) -> int:
    """Прогоняет файлы движками приложения и пишет JSON-отчёт."""
    from localtranscriber.cancellation import CancelToken
    from localtranscriber.engines.ocr_engine import OcrEngine
    from localtranscriber.engines.whisper_engine import WhisperEngine
    from localtranscriber.models_setup import whisper_model_path
    from localtranscriber.pdf import PdfProcessor
    from localtranscriber.router import JobKind, detect_kind

    items: list[dict[str, object]] = []
    whisper = WhisperEngine(
        "small", cpu_threads=8, language="en", model_path=whisper_model_path("small")
    )
    ocr: OcrEngine | None = None
    ok = True
    for raw in paths:
        path = Path(raw)
        kind = detect_kind(path)
        started = time.perf_counter()
        item: dict[str, object] = {"path": path.name, "kind": str(kind)}
        try:
            if kind is JobKind.SPEECH:
                processor = whisper
            else:
                ocr = ocr or OcrEngine()
                processor = PdfProcessor(ocr) if kind is JobKind.PDF else ocr
            result = processor.process(path, cancel=CancelToken(), progress=lambda *_: None)
            item["chars"] = len(result.text)
            item["sample"] = result.text.strip()[:80]
        except Exception as exc:  # noqa: BLE001 - отчёт должен собраться полностью
            ok = False
            item["error"] = f"{type(exc).__name__}: {exc}"
        item["seconds"] = round(time.perf_counter() - started, 2)
        items.append(item)
    payload: dict[str, object] = {
        "frozen": bool(getattr(sys, "frozen", False)),
        "ok": ok,
        "items": items,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 1


def run() -> int:
    if "--selftest" in sys.argv:
        index = sys.argv.index("--selftest")
        rest = sys.argv[index + 1 :]
        out = Path(rest[0]) if rest else Path("selftest.json")
        return run_selftest(rest[1:], out)
    try:
        return main(sys.argv[1:])
    except BaseException:  # noqa: BLE001 - в сборке без консоли нужен видимый след
        from localtranscriber.config import logs_dir

        logs_dir().mkdir(parents=True, exist_ok=True)
        crash = logs_dir() / "crash.log"
        crash.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "LocalTranscriber",
                "Приложение не смогло запуститься.\n"
                f"Подробности записаны в файл:\n{crash}",
            )
            root.destroy()
        except Exception:  # noqa: BLE001 - окно могло не создаться
            pass
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(run())
