# Самопроверка разработчика: TASK-0002 (порт на macOS, сборка `.app`)

Дата: 2026-11-13
Автор: developer. Независимые tester/reviewer не запускались (причина та же, что в TASK-0001:
лимит бесплатных моделей). Это самопроверка, а не `test-report.md`/`review-report.md`.

## 1. Локальные проверки (Windows)

| Проверка | Результат |
|---|---|
| `pytest -o addopts="" -q` | 106 passed, 1 skipped |
| `ruff check .` | All checks passed |
| `mypy src` | Success: 22 файла |
| `scripts\gui_smoke.py` | GUI smoke: OK (3 файла) |
| `scripts\build_exe.ps1` + `--selftest` | exit 0, отчёт `ok: true` |
| `--diagnose` внутри собранного exe | exit 0, `frozen: true` |
| `bash -n scripts/run.sh scripts/build_mac.sh` | 0 ошибок |
| Preflight колёс (`pip download --platform macosx_14_0_arm64 --python-version 3.13`) | все зависимости найдены |

## 2. Сборка в GitHub Actions

Workflow: `.github/workflows/build-macos.yml`, раннер `macos-15` (arm64), Python 3.13.

| Прогон | Тег | Итог | Что было сделано |
|---|---|---|---|
| №1 | `v0.1.0` | cancelled | macOS 14 снят с поддержки → `runs-on: macos-15` |
| №2 | `v0.1.1` | failure (тесты) | нет editable-установки → `pythonpath = ["src"]` |
| №3 | `v0.1.2` | cancelled | раннер не выделен (дефицит arm64) |
| №4 | `v0.1.3` | failure (тесты) | — |
| №5 | `v0.1.4` | cancelled | раннер не выделен |
| №6 | `v0.1.5` | failure (проверки) | добавлены аннотации и `set +e` |
| №7 | `v0.1.6` | failure (mypy) | найдено: `ctypes.windll` вне Windows |
| №8 | `v0.1.7` | **success** | сборка `.app`, zip, артефакт |

Прогон №8 — <https://github.com/GusselnikovSergey/LocalTranscriber/actions/runs/43483275683>

Шаги: checkout → setup-python 3.13 → установка зависимостей (+ `pip install -e .`) →
`Environment info` → `pytest` + `ruff` + `mypy` на macOS → `build_mac.sh` (PyInstaller onedir,
ad-hoc `codesign`, `--diagnose`, `ditto` zip) → upload artifact.

Артефакт: `LocalTranscriber-macos-arm64`, 224 МБ (zip с `LocalTranscriber.app`),
digest `sha256:7cee0af951cf9ccc86a2d15471494cf902ea0445ccd565382d3c4b8caea97829`,
хранится до 2027-02-11.

## 3. Что подтверждено и что нет

Подтверждено:

- Код собирается и проходит все проверки на macOS/Python 3.13 (pytest, ruff, mypy) — то есть
  порт не содержит Windows-only кода, ломающего macOS.
- PyInstaller создаёт `.app`; `--diagnose` внутри `.app` импортирует `faster_whisper`,
  `ctranslate2`, `onnxruntime`, `av`, `pymupdf`, `PIL`, `numpy`, `rapidocr`, `tkinter`,
  `tkinterdnd2` — иначе шаг сборки упал бы (в скрипте `set -e`).
- `codesign --deep --sign -` проходит, zip создаётся, артефакт загружается.

Не подтверждено (требует живого Mac):

- Запуск `.app` двойным кликом/через «правый клик → Открыть», отсутствие предупреждений
  Gatekeeper на конкретной машине.
- Скачивание модели и реальное распознавание речи на macOS (в CI моделей нет).
- Поведение `open` на папке результатов, `Cmd+O`/`Cmd+S`, drag&drop на macOS.
- Работа на Intel-Mac: сборка arm64; для Intel нужен отдельный прогон на `macos-15-intel`.

## 4. Ограничения проверки

1. Независимая проверка (tester/reviewer) не выполнялась — лимит бесплатных моделей.
   Приёмка задачи остаётся `pending` до ручного теста заказчика на Mac.
2. Сборка подписана ad-hoc: Developer ID и нотаризации нет (нет учётной записи Apple).
3. Артефакты GitHub Actions скачиваются только после входа в GitHub — это ограничение
   платформы, а не сборки.
