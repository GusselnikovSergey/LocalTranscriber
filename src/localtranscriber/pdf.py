"""PDF: текстовый слой PyMuPDF и OCR для страниц-сканов."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .cancellation import CancelToken
from .engines.base import ProgressCallback, Result
from .errors import PdfError
from .textformat import pages_to_text

_log = logging.getLogger(__name__)

DEFAULT_DPI = 300
# 10 символов хватает, чтобы отличить настоящий текстовый слой (заголовок,
# короткая строка) от пустой страницы; 40 отправляло на OCR целые страницы
# с одной строкой текста.
MIN_TEXT_LAYER_CHARS = 10


class ImageTextRecognizer(Protocol):
    """Минимальный контракт OCR-движка для PDF-конвейера."""

    def recognize_image(self, image: object) -> list[str]: ...


@dataclass(slots=True)
class PageText:
    number: int
    text: str
    source: str  # "text" | "ocr" | "empty"


def page_has_text(text: str, *, min_chars: int = MIN_TEXT_LAYER_CHARS) -> bool:
    """Страницу считаем текстовой, если в слое достаточно символов."""
    compact = "".join(str(text).split())
    return len(compact) >= min_chars


def extract_pdf(
    path: str | Path,
    *,
    ocr: ImageTextRecognizer | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressCallback | None = None,
    dpi: int = DEFAULT_DPI,
    min_chars: int = MIN_TEXT_LAYER_CHARS,
) -> Result:
    """Извлекает текст постранично, при необходимости распознавая сканы."""
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover
        raise PdfError("Библиотека PyMuPDF не установлена") from exc

    try:
        document = pymupdf.open(str(path))
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"Не удалось открыть PDF: {exc}") from exc

    with document:
        if getattr(document, "needs_pass", False):
            raise PdfError("PDF защищён паролем — снимите защиту и повторите")
        total = document.page_count
        if total == 0:
            raise PdfError("В PDF нет страниц")

        pages: list[PageText] = []
        for index in range(total):
            if cancel is not None:
                cancel.raise_if_cancelled()
            page = document[index]
            source = "text"
            text = page.get_text("text") or ""
            if not page_has_text(text, min_chars=min_chars):
                if ocr is None:
                    source = "empty"
                    text = text.strip()
                else:
                    source = "ocr"
                    text = _ocr_page(page, ocr, dpi=dpi, pymupdf_module=pymupdf)
            pages.append(PageText(number=index + 1, text=text.strip(), source=source))
            if progress is not None:
                progress((index + 1) / total, f"Страница {index + 1} из {total}")

    text_result = pages_to_text([page.text for page in pages])
    ocr_pages = sum(1 for page in pages if page.source == "ocr")
    _log.info(
        "PDF %s: страниц=%d, OCR=%d", Path(path).name, len(pages), ocr_pages
    )
    return Result(
        kind="pdf",
        text=text_result,
        pages=[page.text for page in pages],
        duration=0.0,
        meta={
            "engine": "pymupdf+rapidocr" if ocr_pages else "pymupdf",
            "pages": len(pages),
            "ocr_pages": ocr_pages,
            "page_sources": [page.source for page in pages],
        },
    )


def _ocr_page(
    page: Any, ocr: ImageTextRecognizer, *, dpi: int, pymupdf_module: Any
) -> str:
    colorspace = pymupdf_module.csRGB
    pixmap = page.get_pixmap(dpi=dpi, colorspace=colorspace, alpha=False)
    import numpy as np

    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    lines = ocr.recognize_image(image)
    return "\n".join(lines)


def page_texts(result: Result) -> Sequence[str]:
    """Удобный доступ к тексту страниц из результата."""
    return result.pages


class PdfProcessor:
    """Адаптер PDF-конвейера под общий интерфейс движка."""

    name = "pdf"

    def __init__(self, ocr: ImageTextRecognizer | None) -> None:
        self.ocr = ocr

    def process(
        self, path: Path, *, cancel: CancelToken, progress: ProgressCallback
    ) -> Result:
        return extract_pdf(path, ocr=self.ocr, cancel=cancel, progress=progress)
