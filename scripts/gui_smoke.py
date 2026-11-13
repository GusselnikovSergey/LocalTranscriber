"""Проверка GUI без ручного участия: окно, очередь, обработка, автосохранение.

Пример: python scripts/gui_smoke.py --data testdata/generated
"""

from __future__ import annotations

import argparse
import time
import tkinter as tk
from pathlib import Path

from localtranscriber.config import Settings
from localtranscriber.jobs import STATUS_DONE
from localtranscriber.ui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="testdata/generated")
    parser.add_argument("--out", default="testdata/output")
    parser.add_argument("--audio", default="", help="необязательный аудиофайл для сквозной проверки речи")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--model", default="small", help="модель речи для аудиофайла")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    data = Path(args.data)
    files = [data / "sample.png", data / "digital.pdf", data / "scanned.pdf"]
    if args.audio:
        files.append(Path(args.audio))
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        print("Нет файлов: " + ", ".join(missing))
        return 2

    root = tk.Tk()
    window = MainWindow(
        root,
        Settings(output_dir=args.out, language=args.language, model_size=args.model),
    )
    root.update()
    window._add_paths([str(path) for path in files])
    root.update()
    print(f"Строк в списке: {len(window.tree.get_children())}")

    window._start()
    deadline = time.time() + args.timeout
    while window.jobs.is_running and time.time() < deadline:
        root.update()
        time.sleep(0.05)
    # Даём UI обработать оставшиеся события: автосохранение последнего файла.
    settle = time.time() + 2.0
    while time.time() < settle:
        root.update()
        time.sleep(0.05)
    root.update()

    for job in window.jobs.jobs:
        print(f"{job.path.name}: {job.status} — {job.message}")
    if not all(job.status == STATUS_DONE for job in window.jobs.jobs):
        root.destroy()
        return 1

    window.tree.selection_set("0")
    root.update()
    text = window.editor.get_text()
    print("Результат OCR:", text.splitlines()[0] if text else "<пусто>")
    if args.audio:
        index = len(window.jobs.jobs) - 1
        window.tree.selection_set(str(index))
        root.update()
        speech = window.editor.get_text().strip()
        print("Результат речи:", speech[:200] if speech else "<пусто>")
    root.destroy()
    print("GUI smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
