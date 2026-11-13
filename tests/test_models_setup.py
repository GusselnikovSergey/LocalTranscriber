from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from localtranscriber import models_setup
from localtranscriber.cancellation import CancelToken
from localtranscriber.errors import CancelledError, ModelUnavailableError


class FakeResponse:
    def __init__(self, status_code: int, chunks: list[bytes]) -> None:
        self.status_code = status_code
        self._chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size: int = 0) -> list[bytes]:
        _ = chunk_size
        return self._chunks

    def close(self) -> None:
        self.closed = True


def install(monkeypatch, responses: list[FakeResponse]) -> list[dict]:
    calls: list[dict] = []
    pending = list(responses)

    def fake_get(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        if not pending:
            raise AssertionError("лишний HTTP-запрос")
        return pending.pop(0)

    monkeypatch.setattr(models_setup, "http_get", fake_get)
    monkeypatch.setattr(models_setup.time, "sleep", lambda _seconds: None)
    return calls


def test_download_resumes_from_part_file(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "model.bin"
    part = tmp_path / "model.bin.part"
    part.write_bytes(b"1234")
    calls = install(monkeypatch, [FakeResponse(206, [b"5678"])])
    received: list[int] = []

    models_setup.download_file(
        "https://example/hf", target, expected_size=8, on_bytes=received.append
    )

    assert calls[0]["headers"] == {"Range": "bytes=4-"}
    assert target.read_bytes() == b"12345678"
    assert not part.exists()
    assert received == [8]


def test_download_restarts_when_server_ignores_range(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "model.bin"
    (tmp_path / "model.bin.part").write_bytes(b"old")
    install(monkeypatch, [FakeResponse(200, [b"newdata"])])

    models_setup.download_file("https://example/hf", target, expected_size=7)

    assert target.read_bytes() == b"newdata"


def test_download_retries_and_keeps_partial(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "model.bin"
    install(
        monkeypatch,
        [
            FakeResponse(206, [b"1234"]),
            FakeResponse(206, [b"5678"]),
            FakeResponse(206, [b"9012"]),
        ],
    )
    # Каждая попытка отдаёт только часть ожидаемого — файл не считается готовым.
    with pytest.raises(ModelUnavailableError):
        models_setup.download_file("https://example/hf", target, expected_size=100)

    assert not target.exists()
    assert (tmp_path / "model.bin.part").read_bytes() == b"123456789012"


def test_download_keeps_data_on_cancel(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "model.bin"
    cancel = CancelToken()
    cancel.cancel()
    install(monkeypatch, [FakeResponse(200, [b"1234"])])

    with pytest.raises(CancelledError):
        models_setup.download_file(
            "https://example/hf", target, expected_size=8, cancel=cancel
        )

    assert not target.exists()
    assert (tmp_path / "model.bin.part").exists()


def test_download_rejects_oversized_payload(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "model.bin"
    install(monkeypatch, [FakeResponse(200, [b"123456789"])])

    with pytest.raises(ModelUnavailableError):
        models_setup.download_file("https://example/hf", target, expected_size=4)


def test_download_verifies_sha256(monkeypatch, tmp_path: Path) -> None:
    payload = b"model-weights"
    digest = hashlib.sha256(payload).hexdigest()
    target = tmp_path / "model.bin"
    install(monkeypatch, [FakeResponse(200, [payload])])

    models_setup.download_file(
        "https://example/hf", target, expected_size=len(payload), expected_sha256=digest
    )

    assert target.read_bytes() == payload


def test_download_discards_corrupted_file(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "model.bin"
    install(
        monkeypatch,
        [
            FakeResponse(200, [b"broken"]),
            FakeResponse(200, [b"broken"]),
            FakeResponse(200, [b"broken"]),
        ],
    )

    with pytest.raises(ModelUnavailableError):
        models_setup.download_file(
            "https://example/hf",
            target,
            expected_size=6,
            expected_sha256=hashlib.sha256(b"good!!").hexdigest(),
        )

    assert not target.exists()
    assert not (tmp_path / "model.bin.part").exists()


def test_download_restarts_after_416(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "model.bin"
    (tmp_path / "model.bin.part").write_bytes(b"old")
    install(monkeypatch, [FakeResponse(416, []), FakeResponse(200, [b"newdata"])])

    models_setup.download_file("https://example/hf", target, expected_size=7)

    assert target.read_bytes() == b"newdata"
    assert not (tmp_path / "model.bin.part").exists()


def test_repo_files_wraps_network_error(monkeypatch) -> None:
    def boom(url: str, **kwargs):
        raise OSError("сеть недоступна")

    monkeypatch.setattr(models_setup, "http_get", boom)

    with pytest.raises(ModelUnavailableError, match="интернет"):
        models_setup.repo_files("Systran/faster-whisper-small")


def test_repo_files_rejects_unexpected_payload(monkeypatch) -> None:
    class ListResponse(FakeResponse):
        def json(self):
            return ["не тот ответ"]

    install(monkeypatch, [ListResponse(200, [])])

    with pytest.raises(ModelUnavailableError, match="неожиданный ответ"):
        models_setup.repo_files("Systran/faster-whisper-small")


def test_model_present_requires_all_required_files(tmp_path: Path) -> None:
    assert not models_setup.model_present(tmp_path)
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "model.bin").write_bytes(b"weights")
    # Конфиг и веса без токенизатора — модель ещё не готова.
    assert not models_setup.model_present(tmp_path)
    assert models_setup.missing_files(tmp_path) == ["tokenizer.json", "vocabulary.txt"]

    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    assert not models_setup.model_present(tmp_path)
    (tmp_path / "vocabulary.txt").write_text("a\n", encoding="utf-8")

    assert models_setup.model_present(tmp_path)
    assert models_setup.missing_files(tmp_path) == []


def test_ensure_whisper_model_downloads_only_missing_files(
    monkeypatch, tmp_path: Path
) -> None:
    destination = tmp_path / "whisper-small"
    destination.mkdir()
    (destination / "config.json").write_text("{}", encoding="utf-8")
    (destination / "model.bin").write_bytes(b"weights")

    files = [
        models_setup.ModelFile("config.json", 2),
        models_setup.ModelFile("model.bin", 7),
        models_setup.ModelFile("tokenizer.json", 11),
        models_setup.ModelFile("vocabulary.txt", 5),
    ]
    monkeypatch.setattr(models_setup, "repo_files", lambda repo: files)
    monkeypatch.setattr(
        models_setup, "model_directory", lambda size, root=None: destination
    )
    downloaded: list[str] = []

    def fake_download(url: str, target: Path, **kwargs) -> None:
        downloaded.append(target.name)
        target.write_bytes(b"x" * int(kwargs["expected_size"]))

    monkeypatch.setattr(models_setup, "download_file", fake_download)
    progress: list[float] = []

    result = models_setup.ensure_whisper_model(
        "small", progress=lambda fraction, _message: progress.append(fraction)
    )

    assert result == destination
    assert downloaded == ["tokenizer.json", "vocabulary.txt"]
    assert progress[-1] == 1.0
    assert models_setup.model_present(destination)


def test_ensure_whisper_model_reports_missing_files_after_download(
    monkeypatch, tmp_path: Path
) -> None:
    destination = tmp_path / "whisper-small"
    files = [models_setup.ModelFile("config.json", 2)]
    monkeypatch.setattr(models_setup, "repo_files", lambda repo: files)
    monkeypatch.setattr(
        models_setup, "model_directory", lambda size, root=None: destination
    )
    monkeypatch.setattr(models_setup, "download_file", lambda *args, **kwargs: None)

    with pytest.raises(ModelUnavailableError, match="model.bin"):
        models_setup.ensure_whisper_model("small")
