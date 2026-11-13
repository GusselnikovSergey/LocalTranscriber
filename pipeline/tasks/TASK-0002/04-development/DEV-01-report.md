# Отчёт о разработке: TASK-0002

Дата: 2026-11-13
Автор: developer
Основание: план `02-plan.md` (Decision: approved).

## 1. Что сделано

| Требование | Изменение |
|---|---|
| FR-01 | `config.py`: на macOS настройки и модели → `~/Library/Application Support/LocalTranscriber`, логи → `~/Library/Logs/LocalTranscriber`; Windows-ветка не изменилась |
| FR-02 | новый `platform_utils.py`: `open_in_file_manager()` — `os.startfile` / `open` / `xdg-open`; `main_window._open_output()` использует его |
| FR-03 | `modifier_label()` (`Cmd`/`Ctrl`) в меню; `shortcut_bindings()` добавляет `<Command-o>`/`<Command-s>` на macOS, `<Control-…>` остаётся |
| FR-04 | `scripts/run.sh` — запуск из исходников (venv, зависимости, `PYTHONPATH=src`) |
| FR-05 | `scripts/build_mac.sh` — PyInstaller `.app`, ad-hoc `codesign`, диагностика, zip |
| FR-06 | `.github/workflows/build-macos.yml` — `macos-15`, Python 3.13, тесты/ruff/mypy, сборка, артефакт |
| FR-07 | поведение Windows не менялось; регрессия зелёная |

Дополнительно: в `scripts/launcher.py` добавлен режим `--diagnose отчёт.json` —
импортирует `faster_whisper`, `ctranslate2`, `onnxruntime`, `av`, `pymupdf`, `PIL`,
`numpy`, `rapidocr`, `tkinter`, `tkinterdnd2` и пишет версии. Нужен, чтобы в CI поймать
отсутствующие dylib без скачивания моделей (в CI модели не скачиваются).

## 2. Проверки

| Проверка | Результат |
|---|---|
| `pytest -o addopts="" -q` | **106 passed, 1 skipped** (было 94; +12 новых тестов) |
| `ruff check .` | All checks passed |
| `mypy src` | Success: 22 файла |
| `gui_smoke.py` | GUI smoke: OK (3 файла) |
| `build_exe.ps1` + `--selftest` | exit 0, отчёт `ok: true` |
| `--diagnose` внутри exe | exit 0, `frozen: true`, все модули импортируются |
| Preflight колёс под macOS arm64 / cp313 | все пакеты найдены (`pip download --platform macosx_14_0_arm64`) |
| `bash -n scripts/*.sh` | 0 ошибок |
| YAML workflow | разбирается, job `build` |

Важно: `pip download --platform macosx_11_0_arm64` даёт ложный минус на `av==19.0.2`
(колёса PyAV собраны под macOS 14), при `macosx_14_0_arm64` всё скачивается. Поэтому
workflow закреплён на `macos-15` (macOS 14 в Actions снят с поддержки 02.11.2026).

## 3. Новые тесты

- `tests/test_platform_utils.py` — открытие папки на win32/darwin/linux, отсутствие
  команды не роняет приложение, подписи и привязки горячих клавиш.
- `tests/test_platform_paths.py` — каталоги macOS, сохранение Windows-переменных
  `%APPDATA%`/`%LOCALAPPDATA%`, игнорирование Windows-переменных на macOS.

## 4. Ограничения

- Сборка подписана ad-hoc: первый запуск — правый клик → «Открыть» (или
  `xattr -dr com.apple.quarantine`). Developer ID/нотаризация не делались (нет
  учётной записи Apple Developer).
- Собирается под архитектуру раннера (Apple Silicon). Intel-Mac и universal2 — вне scope.
- `.app` не проверялся на живом Mac: у заказчика Mac нет. Первый прогон workflow — и
  есть проверка; после него нужен запуск `.app` на Mac.
- Модели в `.app` не входят, скачиваются при первом запуске.
