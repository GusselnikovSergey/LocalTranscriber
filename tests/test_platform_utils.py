"""Платформенные помощники: открытие папки и горячие клавиши (TASK-0002)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from localtranscriber import platform_utils


def test_open_folder_windows_uses_startfile(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        platform_utils.os, "startfile", lambda target: calls.append(target), raising=False
    )
    platform_utils.open_in_file_manager(tmp_path)
    assert calls == [str(tmp_path)]


def test_open_folder_macos_uses_open(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []

    class FakePopen:
        def __init__(self, command, **kwargs):  # noqa: ANN001
            commands.append(list(command))

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform_utils.subprocess, "Popen", FakePopen)
    platform_utils.open_in_file_manager(tmp_path)
    assert commands == [["open", str(tmp_path)]]


def test_open_folder_linux_uses_xdg_open(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []

    class FakePopen:
        def __init__(self, command, **kwargs):  # noqa: ANN001
            commands.append(list(command))

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(platform_utils.subprocess, "Popen", FakePopen)
    platform_utils.open_in_file_manager(tmp_path)
    assert commands == [["xdg-open", str(tmp_path)]]


def test_open_folder_ignores_missing_command(monkeypatch, tmp_path: Path) -> None:
    def fail(command, **kwargs):  # noqa: ANN001
        raise FileNotFoundError(command)

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform_utils.subprocess, "Popen", fail)
    platform_utils.open_in_file_manager(tmp_path)  # не должно бросить исключение


@pytest.mark.parametrize(
    ("platform", "label"),
    [("darwin", "Cmd"), ("win32", "Ctrl"), ("linux", "Ctrl")],
)
def test_modifier_label(monkeypatch, platform: str, label: str) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert platform_utils.modifier_label() == label


def test_shortcuts_macos_accept_both_keys(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert platform_utils.shortcut_bindings("o") == ("<Command-o>", "<Control-o>")


def test_shortcuts_windows_use_control(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert platform_utils.shortcut_bindings("s") == ("<Control-s>",)
