"""Генерирует тестовые файлы: изображение, PDF с текстом, сканированный PDF, WAV.

Пример: python scripts/make_testdata.py --out testdata/generated
"""

from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = (
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf",
)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def make_image(path: Path) -> None:
    image = Image.new("RGB", (1000, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 40), "Локальная транскрибация текста", fill="black", font=_font(40))
    draw.text((30, 120), "Проверка распознавания: строка 2", fill="black", font=_font(36))
    draw.text((30, 200), "Москва, 2026 год", fill="black", font=_font(36))
    image.save(path)


def make_text_pdf(path: Path) -> None:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 100), "Digital PDF text layer sample", fontsize=18, fontname="helv")
    page.insert_text((72, 140), "Second line of the document.", fontsize=14, fontname="helv")
    document.save(str(path))
    document.close()


def make_scanned_pdf(path: Path, image_path: Path) -> None:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(pymupdf.Rect(40, 40, 555, 220), filename=str(image_path))
    document.save(str(path))
    document.close()


def make_tone_wav(path: Path, seconds: float = 3.0, rate: int = 16000) -> None:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    signal = 0.2 * np.sin(2 * math.pi * 440 * t) + 0.1 * np.sin(2 * math.pi * 220 * t)
    pcm = np.int16(signal * 32767)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="testdata/generated")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    image = out / "sample.png"
    make_image(image)
    make_text_pdf(out / "digital.pdf")
    make_scanned_pdf(out / "scanned.pdf", image)
    make_tone_wav(out / "tone.wav")
    print(f"Готово: {out.resolve()}")
    for file in sorted(out.iterdir()):
        print(f" - {file.name} ({file.stat().st_size} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
