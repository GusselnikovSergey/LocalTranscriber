from __future__ import annotations

import json
import os

from localtranscriber.config import (
    DEFAULT_MODEL,
    MODEL_SIZES,
    Settings,
    load_settings,
    save_settings,
)


def test_defaults_are_valid() -> None:
    settings = Settings().normalized()
    assert settings.model_size in MODEL_SIZES
    assert settings.language == "ru"
    assert 1 <= settings.cpu_threads <= max(1, (os.cpu_count() or 4) * 2)
    assert settings.output_dir


def test_save_and_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    original = Settings(
        model_size="large-v3",
        language="auto",
        cpu_threads=4,
        output_dir=str(tmp_path / "out"),
        show_timestamps=True,
    )
    save_settings(original, path)
    loaded = load_settings(path)
    assert loaded.model_size == "large-v3"
    assert loaded.language == "auto"
    assert loaded.cpu_threads == 4
    assert loaded.show_timestamps is True
    assert loaded.output_dir == str(tmp_path / "out")


def test_broken_json_falls_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{это не json", encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.model_size == DEFAULT_MODEL


def test_unknown_values_are_normalized(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "model_size": "gigantic",
                "language": "klingon",
                "cpu_threads": "много",
                "unknown_key": 1,
            }
        ),
        encoding="utf-8",
    )
    loaded = load_settings(path)
    assert loaded.model_size == DEFAULT_MODEL
    assert loaded.language == "ru"
    assert isinstance(loaded.cpu_threads, int)
    assert loaded.cpu_threads >= 1


def test_threads_are_clamped(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"cpu_threads": 100000}), encoding="utf-8")
    assert load_settings(path).cpu_threads >= 1
    path.write_text(json.dumps({"cpu_threads": -5}), encoding="utf-8")
    assert load_settings(path).cpu_threads == 1


def test_missing_file_returns_defaults(tmp_path) -> None:
    loaded = load_settings(tmp_path / "nope.json")
    assert loaded.model_size == DEFAULT_MODEL
