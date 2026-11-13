"""OCR изображений локально: RapidOCR (ONNX Runtime) с русской моделью."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..cancellation import CancelToken
from ..config import models_dir
from ..errors import ModelUnavailableError
from ..router import IMAGE_EXTS
from .base import ProgressCallback, Result

_log = logging.getLogger(__name__)

OCR_MODELS_SUBDIR = "ocr"


def ocr_models_root(root: Path | None = None) -> Path:
    base = root or models_dir()
    return base / OCR_MODELS_SUBDIR


def sort_text_lines(boxes: Sequence[Any], texts: Sequence[str]) -> list[str]:
    """Упорядочивает найденные блоки построчно: сверху вниз, слева направо.

    ``boxes`` — четырёхточечные контуры из RapidOCR, ``texts`` — их содержимое.
    """
    items: list[dict[str, Any]] = []
    for box, text in zip(boxes, texts, strict=False):
        clean = str(text or "").strip()
        if not clean:
            continue
        points = np.asarray(box, dtype=float).reshape(-1, 2)
        if points.size == 0:
            continue
        top = float(points[:, 1].min())
        bottom = float(points[:, 1].max())
        left = float(points[:, 0].min())
        items.append(
            {
                "text": clean,
                "center": (top + bottom) / 2,
                "height": max(bottom - top, 1.0),
                "left": left,
            }
        )
    if not items:
        return []

    heights = sorted(item["height"] for item in items)
    median_height = heights[len(heights) // 2]
    tolerance = max(median_height * 0.6, 6.0)

    items.sort(key=lambda item: (item["center"], item["left"]))
    lines: list[list[dict[str, Any]]] = []
    for item in items:
        if not lines:
            lines.append([item])
            continue
        current = lines[-1]
        baseline = sum(entry["center"] for entry in current) / len(current)
        if abs(item["center"] - baseline) <= tolerance:
            current.append(item)
        else:
            lines.append([item])

    ordered: list[str] = []
    for line in lines:
        line.sort(key=lambda entry: entry["left"])
        ordered.append(" ".join(entry["text"] for entry in line))
    return ordered


class OcrEngine:
    """Ленивая обёртка над ``rapidocr.RapidOCR``."""

    name = "rapidocr"

    def __init__(
        self,
        *,
        lang: str = "cyrillic",
        model_root: Path | None = None,
        use_cls: bool = False,
        engine_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.lang = lang
        self.model_root = model_root or ocr_models_root()
        self.use_cls = use_cls
        self._engine: Any | None = None
        self._engine_factory = engine_factory

    @property
    def display_name(self) -> str:
        return f"RapidOCR ({self.lang})"

    def _load(self) -> Any:
        if self._engine is not None:
            return self._engine
        if self._engine_factory is not None:
            self._engine = self._engine_factory()
            return self._engine

        try:
            from rapidocr import RapidOCR
            from rapidocr.utils.typings import LangRec, ModelType, OCRVersion
        except ImportError as exc:  # pragma: no cover
            raise ModelUnavailableError(
                "Библиотека RapidOCR не установлена. Запустите run.ps1 или "
                "python -m pip install -r requirements.txt"
            ) from exc

        lang_enum = getattr(LangRec, self.lang.upper(), LangRec.CYRILLIC)
        self.model_root.mkdir(parents=True, exist_ok=True)
        params = {
            "Global.model_root_dir": str(self.model_root),
            "Global.log_level": "error",
            "Global.use_cls": self.use_cls,
            "Rec.lang_type": lang_enum,
            # PP-OCRv5 — актуальная версия с моделью cyrillic_PP-OCRv5_rec_mobile
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
        }
        started = time.perf_counter()
        try:
            engine = RapidOCR(params=params)
        except Exception as exc:  # noqa: BLE001
            _log.exception("Не удалось инициализировать RapidOCR")
            raise ModelUnavailableError(
                "Не удалось загрузить модели OCR. Проверьте интернет-соединение при "
                f"первом запуске и свободное место на диске. Подробности: {exc}"
            ) from exc
        _log.info("RapidOCR готов за %.1f с", time.perf_counter() - started)
        self._engine = engine
        return engine

    def recognize_image(self, image: Any, *, text_score: float | None = None) -> list[str]:
        """Распознаёт текст на изображении (путь, PIL.Image или numpy-массив)."""
        engine = self._load()
        kwargs = {"text_score": text_score} if text_score is not None else {}
        try:
            output = engine(image, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailableError(f"Ошибка распознавания изображения: {exc}") from exc
        if output is None:
            return []
        texts = getattr(output, "txts", None) or ()
        boxes = getattr(output, "boxes", None)
        if boxes is None:
            return [str(text).strip() for text in texts if str(text).strip()]
        return sort_text_lines(list(boxes), list(texts))

    def process(
        self, path: Path, *, cancel: CancelToken, progress: ProgressCallback
    ) -> Result:
        suffix = Path(path).suffix.lower()
        if suffix not in IMAGE_EXTS:
            raise ModelUnavailableError(f"Файл {suffix} не является изображением")

        progress(0.05, "Подготовка изображения")
        try:
            from PIL import Image, ImageOps
        except ImportError as exc:  # pragma: no cover
            raise ModelUnavailableError("Библиотека Pillow не установлена") from exc

        try:
            with Image.open(path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                array = np.array(image)
        except OSError as exc:
            raise ModelUnavailableError(f"Не удалось открыть изображение: {exc}") from exc

        cancel.raise_if_cancelled()
        progress(0.2, "Распознавание текста")
        started = time.perf_counter()
        lines = self.recognize_image(array)
        cancel.raise_if_cancelled()
        elapsed = time.perf_counter() - started
        text = "\n".join(lines)
        progress(1.0, "Готово")
        _log.info(
            "OCR %s: строк=%d за %.1f с", Path(path).name, len(lines), elapsed
        )
        return Result(
            kind="image",
            text=text,
            language="",
            duration=0.0,
            meta={"engine": self.name, "lines": len(lines), "elapsed": round(elapsed, 2)},
        )


__all__ = ["OcrEngine", "ocr_models_root", "sort_text_lines"]
