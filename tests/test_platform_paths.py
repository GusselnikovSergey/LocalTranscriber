"""Стандартные каталоги настроек и данных на разных платформах (TASK-0002)."""

from __future__ import annotations

import sys
from pathlib import Path

from localtranscriber import config


def test_macos_directories(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    support = tmp_path / "Library" / "Application Support" / "LocalTranscriber"
    assert config.appdata_dir() == support
    assert config.localappdata_dir() == support
    assert config.models_dir() == support / "models"
    assert config.settings_path() == support / "settings.json"
    assert config.logs_dir() == tmp_path / "Library" / "Logs" / "LocalTranscriber"


def test_windows_directories_keep_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

    assert config.appdata_dir() == tmp_path / "Roaming" / "LocalTranscriber"
    assert config.localappdata_dir() == tmp_path / "Local" / "LocalTranscriber"
    assert config.models_dir() == tmp_path / "Local" / "LocalTranscriber" / "models"
    assert config.logs_dir() == tmp_path / "Local" / "LocalTranscriber" / "logs"


def test_macos_ignores_windows_environment(monkeypatch, tmp_path: Path) -> None:
    """Переменные Windows не должны уводить пути на macOS."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "wrong"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "wrong-local"))

    expected = tmp_path / "Library" / "Application Support" / "LocalTranscriber"
    assert config.appdata_dir() == expected
    assert config.localappdata_dir() == expected
