"""Сетевые помощники: доверие системному хранилищу сертификатов Windows.

Корпоративные прокси и антивирусы часто подменяют TLS-сертификаты. Пакет
``truststore`` заставляет Python использовать хранилище сертификатов Windows,
иначе загрузка моделей падает с ``CERTIFICATE_VERIFY_FAILED``.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)
_installed = False


def ensure_system_trust() -> bool:
    """Один раз подключает системное хранилище сертификатов. Возвращает успех."""
    global _installed
    if _installed:
        return True
    try:
        import truststore

        truststore.inject_into_ssl()
        _installed = True
        _log.info("Используется системное хранилище сертификатов Windows")
        return True
    except Exception as exc:  # noqa: BLE001 - без truststore тоже можно работать
        _log.info("truststore недоступен, используется certifi: %s", exc)
        return False


def http_get(
    url: str,
    *,
    stream: bool = False,
    headers: dict[str, str] | None = None,
    timeout: tuple[int, int] = (15, 60),
) -> Any:
    """GET-запрос с системным доверием сертификатов и без кэширования сжатия."""
    ensure_system_trust()
    import requests

    base_headers = {"Accept-Encoding": "identity"}
    if headers:
        base_headers.update(headers)
    return requests.get(url, stream=stream, headers=base_headers, timeout=timeout)
