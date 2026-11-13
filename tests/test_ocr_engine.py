from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np
import pytest

from localtranscriber.cancellation import CancelToken
from localtranscriber.engines.ocr_engine import OcrEngine, sort_text_lines


def box(left: float, top: float, width: float = 200, height: float = 30) -> list[list[float]]:
    return [
        [left, top],
        [left + width, top],
        [left + width, top + height],
        [left, top + height],
    ]


def test_sort_single_line_left_to_right() -> None:
    boxes = [box(300, 10), box(10, 10), box(150, 12)]
    texts = ["третий", "первый", "второй"]
    assert sort_text_lines(boxes, texts) == ["первый второй третий"]


def test_sort_two_lines() -> None:
    boxes = [box(10, 100), box(10, 10), box(250, 12)]
    texts = ["вторая строка", "первая строка", "продолжение"]
    assert sort_text_lines(boxes, texts) == ["первая строка продолжение", "вторая строка"]


def test_sort_skips_empty_and_invalid() -> None:
    assert sort_text_lines([box(0, 0), box(0, 40)], ["  ", "текст"]) == ["текст"]
    assert sort_text_lines([], []) == []


class FakeEngine:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, image, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            txts=("вторая", "первая"),
            boxes=np.array([box(300, 120), box(20, 20)]),
            scores=(0.9, 0.9),
        )


def test_engine_factory_is_used(tmp_path) -> None:
    fake = FakeEngine()
    engine = OcrEngine(engine_factory=lambda: fake)
    image_path = tmp_path / "image.png"
    from PIL import Image

    Image.new("RGB", (100, 50), "white").save(image_path)
    result = engine.process(image_path, cancel=CancelToken(), progress=lambda *_: None)
    assert fake.calls == 1
    assert result.text.splitlines() == ["первая", "вторая"]
    assert result.meta["lines"] == 2


def test_engine_rejects_non_image(tmp_path) -> None:
    engine = OcrEngine(engine_factory=FakeEngine)
    path = tmp_path / "audio.mp3"
    path.write_bytes(b"")
    from localtranscriber.errors import ModelUnavailableError

    with pytest.raises(ModelUnavailableError):
        engine.process(path, cancel=CancelToken(), progress=lambda *_: None)


@pytest.mark.slow
def test_real_ocr_recognizes_russian(tmp_path) -> None:
    font = "C:/Windows/Fonts/arial.ttf"
    if not os.path.exists(font):
        pytest.skip("нет шрифта arial.ttf")
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1000, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (30, 60),
        "Локальная транскрибация текста",
        fill="black",
        font=ImageFont.truetype(font, 40),
    )
    path = tmp_path / "sample.png"
    image.save(path)

    engine = OcrEngine()
    result = engine.process(path, cancel=CancelToken(), progress=lambda *_: None)
    normalized = result.text.lower().replace(" ", "")
    assert "транскрибация" in normalized
