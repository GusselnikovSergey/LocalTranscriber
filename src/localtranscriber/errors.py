"""Доменные исключения приложения."""

from __future__ import annotations


class LocalTranscriberError(Exception):
    """Базовая ошибка с человекочитаемым сообщением."""


class UnsupportedFileError(LocalTranscriberError):
    """Расширение файла не поддерживается."""


class AudioDecodeError(LocalTranscriberError):
    """Не удалось декодировать звуковую дорожку."""


class ModelUnavailableError(LocalTranscriberError):
    """Модель не найдена и не может быть загружена."""


class PdfError(LocalTranscriberError):
    """Не удалось прочитать PDF."""


class CancelledError(LocalTranscriberError):
    """Задание отменено пользователем."""
