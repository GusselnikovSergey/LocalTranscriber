from __future__ import annotations

import numpy as np
import pymupdf
import pytest

from localtranscriber.cancellation import CancelToken
from localtranscriber.errors import CancelledError, PdfError
from localtranscriber.pdf import PdfProcessor, extract_pdf, page_has_text, pages_to_text


class FakeOcr:
    def __init__(self) -> None:
        self.calls: list[tuple[int, ...]] = []

    def recognize_image(self, image: object) -> list[str]:
        array = np.asarray(image)
        self.calls.append(array.shape)
        return ["распознанная строка 1", "распознанная строка 2"]


def make_text_pdf(path, pages: int = 2) -> None:
    document = pymupdf.open()
    for number in range(pages):
        page = document.new_page()
        # Стандартный шрифт PyMuPDF не умеет кириллицу — для теста достаточно латиницы.
        page.insert_text((72, 72), f"Page {number + 1}. " + "Document text. " * 6)
    document.save(str(path))
    document.close()


def make_scanned_pdf(path) -> None:
    from PIL import Image

    image_path = path.with_suffix(".png")
    Image.new("RGB", (400, 200), "white").save(image_path)

    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(pymupdf.Rect(50, 50, 350, 200), filename=str(image_path))
    document.save(str(path))
    document.close()


def test_page_has_text_threshold() -> None:
    assert page_has_text("Достаточно длинный текст страницы " * 2) is True
    assert page_has_text("коротко") is False
    assert page_has_text("   ") is False


def test_pages_to_text_import() -> None:
    assert pages_to_text(["a"]) == "a"


def test_extract_text_pdf_without_ocr(tmp_path) -> None:
    path = tmp_path / "doc.pdf"
    make_text_pdf(path)
    result = extract_pdf(path)
    assert result.kind == "pdf"
    assert result.meta["ocr_pages"] == 0
    assert "--- стр. 1 ---" in result.text
    assert result.pages[0].startswith("Page 1")


def test_extract_scanned_pdf_uses_ocr(tmp_path) -> None:
    path = tmp_path / "scan.pdf"
    make_scanned_pdf(path)
    ocr = FakeOcr()
    result = extract_pdf(path, ocr=ocr)
    assert result.meta["ocr_pages"] == 1
    assert "распознанная строка 1" in result.text
    assert ocr.calls and ocr.calls[0][2] == 3


def test_protected_pdf_raises(tmp_path) -> None:
    path = tmp_path / "locked.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "секрет")
    document.save(
        str(path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    )
    document.close()
    with pytest.raises(PdfError):
        extract_pdf(path)


def test_cancel_stops_extraction(tmp_path) -> None:
    path = tmp_path / "doc.pdf"
    make_text_pdf(path, pages=3)
    cancel = CancelToken()
    cancel.cancel()
    with pytest.raises(CancelledError):
        extract_pdf(path, cancel=cancel)


def test_processor_adapter(tmp_path) -> None:
    path = tmp_path / "doc.pdf"
    make_scanned_pdf(path)
    processor = PdfProcessor(FakeOcr())
    result = processor.process(path, cancel=CancelToken(), progress=lambda *_: None)
    assert result.kind == "pdf"
    assert "распознанная" in result.text
