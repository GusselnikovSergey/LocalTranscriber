"""Загрузка моделей Whisper с прогрессом и поддержкой отмены."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .cancellation import CancelToken
from .config import models_dir
from .engines.whisper_engine import MODEL_REPOS, model_directory
from .errors import CancelledError, ModelUnavailableError
from .network import http_get

_log = logging.getLogger(__name__)

HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
REQUIRED_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
CHUNK_SIZE = 1 << 20
RETRIES = 3
ProgressCallback = Callable[[float, str], None]


@dataclass(frozen=True)
class ModelFile:
    """Файл модели: имя, размер и sha256 (если сервер его сообщает)."""

    name: str
    size: int
    sha256: str = ""


def model_present(directory: Path) -> bool:
    """Модель готова только когда на месте все обязательные файлы.

    Проверка по одному ``model.bin`` опасна: обрыв загрузки между файлами
    оставлял бы «готовую» модель, которая падает при каждом распознавании.
    """
    return all((directory / name).is_file() for name in REQUIRED_FILES)


def missing_files(directory: Path) -> list[str]:
    return [name for name in REQUIRED_FILES if not (directory / name).is_file()]


def _request(url: str, *, stream: bool = False):
    return http_get(url, stream=stream)


def repo_files(repo: str) -> list[ModelFile]:
    """Список файлов модели и их размеры (через API Hugging Face)."""
    url = f"{HF_ENDPOINT}/api/models/{repo}?blobs=true"
    message = (
        "Не удалось получить список файлов модели. Проверьте интернет-соединение. "
        "Если сеть недоступна, подключите её и нажмите «Обработать» ещё раз."
    )
    try:
        response = _request(url)
    except Exception as exc:  # noqa: BLE001 - любая сетевая ошибка важна пользователю
        raise ModelUnavailableError(f"{message} Подробности: {exc}") from exc
    try:
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailableError(f"{message} Подробности: {exc}") from exc
    finally:
        response.close()
    if not isinstance(payload, dict):
        raise ModelUnavailableError(
            f"{message} Сервер вернул неожиданный ответ вместо списка файлов."
        )
    siblings = payload.get("siblings") or []
    files: list[ModelFile] = []
    for item in siblings:
        name = str(item.get("rfilename", ""))
        if not name or name.startswith(".") or name.endswith(".md"):
            continue
        size = int(item.get("size") or 0)
        digest = str((item.get("lfs") or {}).get("sha256") or "")
        files.append(ModelFile(name=name, size=size, sha256=digest))
    if not files:
        raise ModelUnavailableError(f"Репозиторий модели {repo} пуст или недоступен")
    return files


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def _download_attempt(
    url: str,
    temp: Path,
    *,
    expected_size: int,
    on_bytes: Callable[[int], None] | None,
    cancel: CancelToken | None,
) -> int:
    """Одна попытка скачивания с докачкой через ``Range``. Возвращает размер файла."""
    written = temp.stat().st_size if temp.is_file() else 0
    if expected_size and written > expected_size:
        _log.info("Частичный файл %s больше ожидаемого, скачиваем заново", temp.name)
        temp.unlink(missing_ok=True)
        written = 0
    if expected_size and written == expected_size:
        return written

    headers = {"Range": f"bytes={written}-"} if written else None
    response = http_get(url, stream=True, headers=headers, timeout=(20, 120))
    try:
        if response.status_code == 416:
            if expected_size and written >= expected_size:
                return written
            temp.unlink(missing_ok=True)
            raise ModelUnavailableError(
                "Сервер отклонил докачку, файл будет скачан заново"
            )
        if response.status_code == 206:
            mode = "ab"
        elif response.status_code == 200:
            if written:
                _log.info("Сервер не поддержал докачку, файл скачивается заново")
            written = 0
            mode = "wb"
        else:
            raise ModelUnavailableError(
                f"Сервер вернул код {response.status_code} при загрузке модели"
            )
        temp.parent.mkdir(parents=True, exist_ok=True)
        with temp.open(mode) as handle:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if cancel is not None:
                    cancel.raise_if_cancelled()
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
                if on_bytes is not None:
                    on_bytes(written)
                if expected_size and written > expected_size:
                    raise ModelUnavailableError(
                        "Сервер прислал больше данных, чем ожидалось"
                    )
        if expected_size and written < expected_size:
            raise ModelUnavailableError(
                f"Получено {written} из {expected_size} байт"
            )
        return written
    finally:
        response.close()


def download_file(
    url: str,
    target: Path,
    *,
    expected_size: int = 0,
    expected_sha256: str = "",
    on_bytes: Callable[[int], None] | None = None,
    cancel: CancelToken | None = None,
) -> None:
    """Скачивает файл в ``.part`` с докачкой и переименовывает по завершении.

    Незавершённые данные остаются в ``.part``, поэтому повторный запуск
    продолжает загрузку с того же места, а не начинает её сначала.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            written = _download_attempt(
                url,
                temp,
                expected_size=expected_size,
                on_bytes=on_bytes,
                cancel=cancel,
            )
        except CancelledError:
            _log.info("Загрузка %s отменена, данные сохранены в %s", target.name, temp.name)
            raise
        except OSError as exc:
            raise ModelUnavailableError(f"Не удалось записать файл модели: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            kept = temp.stat().st_size if temp.is_file() else 0
            _log.warning(
                "Попытка %d/%d не удалась (%d байт сохранено): %s",
                attempt,
                RETRIES,
                kept,
                exc,
            )
            if attempt < RETRIES:
                time.sleep(min(2.0 * attempt, 6.0))
            continue
        if expected_sha256:
            actual = sha256_of(temp)
            if actual != expected_sha256:
                temp.unlink(missing_ok=True)
                last_error = ModelUnavailableError(
                    f"Файл {target.name} скачался с ошибкой (контрольная сумма не совпала)"
                )
                _log.warning(
                    "Попытка %d/%d: sha256 %s != %s, файл удалён",
                    attempt,
                    RETRIES,
                    actual[:12],
                    expected_sha256[:12],
                )
                if attempt < RETRIES:
                    time.sleep(min(2.0 * attempt, 6.0))
                continue
        os.replace(temp, target)
        _log.info("Загружен %s (%d байт)", target.name, written)
        return
    raise ModelUnavailableError(
        "Не удалось скачать модель. Проверьте интернет и свободное место на диске: "
        "следующий запуск продолжит загрузку с того же места."
    ) from last_error


def ensure_whisper_model(
    size: str,
    *,
    root: Path | None = None,
    progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
) -> Path:
    """Гарантирует наличие модели и возвращает путь к её каталогу."""
    if size not in MODEL_REPOS:
        raise ModelUnavailableError(f"Неизвестный размер модели: {size}")
    destination = model_directory(size, root)
    if model_present(destination):
        return destination

    repo = MODEL_REPOS[size]
    files = repo_files(repo)
    total = sum(item.size for item in files) or 1
    done = 0

    for item in files:
        if cancel is not None:
            cancel.raise_if_cancelled()
        target = destination / item.name
        if target.is_file() and (item.size == 0 or target.stat().st_size == item.size):
            done += item.size
            continue
        url = f"{HF_ENDPOINT}/{repo}/resolve/main/{item.name}?download=true"
        _log.info(
            "Скачивание %s (%d МБ, осталось файлов: %d)",
            item.name,
            item.size // (1024 * 1024),
            len(missing_files(destination)),
        )
        base = done

        def on_bytes(current: int, *, _base: int = base) -> None:
            if progress is None:
                return
            fraction = min((_base + current) / total, 1.0)
            progress(fraction, f"Загрузка модели {size}: {int(fraction * 100)}%")

        download_file(
            url,
            target,
            expected_size=item.size,
            expected_sha256=item.sha256,
            on_bytes=on_bytes,
            cancel=cancel,
        )
        done = base + item.size

    if not model_present(destination):
        raise ModelUnavailableError(
            f"Модель {size} загружена не полностью (нет файлов: "
            f"{', '.join(missing_files(destination))}). "
            "При следующем запуске загрузка продолжится с того же места."
        )
    if progress is not None:
        progress(1.0, f"Модель {size} готова")
    return destination


def whisper_model_path(size: str) -> Path | None:
    """Путь к готовой модели или ``None``, если её нет локально."""
    directory = model_directory(size)
    return directory if model_present(directory) else None


def models_root() -> Path:
    return models_dir()
