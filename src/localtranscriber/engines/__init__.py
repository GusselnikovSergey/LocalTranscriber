"""Движки распознавания: речь (faster-whisper) и OCR (RapidOCR)."""

from .base import Processor, ProgressCallback, Result

__all__ = ["ProgressCallback", "Processor", "Result"]
