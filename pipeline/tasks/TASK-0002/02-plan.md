# План работ: TASK-0002

## 1. Краткое резюме

PyInstaller не умеет кросс-компиляцию, поэтому `.app` собирается на macOS-раннере
GitHub Actions. Код готовим к macOS: стандартные каталоги, `open` вместо `os.startfile`,
`Command`-клавиши, скрипты `run.sh`/`build_mac.sh`. Логика распознавания не меняется,
поведение на Windows сохраняется полностью.

## 2. Технический подход

| Модуль | Изменение |
|---|---|
| `src/localtranscriber/config.py` | `appdata_dir()`, `localappdata_dir()`, `logs_dir()` учитывают `sys.platform == "darwin"`; на Windows остаются `%APPDATA%`/`%LOCALAPPDATA%` |
| `src/localtranscriber/platform_utils.py` (новый) | `open_in_file_manager(path)` (Windows `os.startfile`, macOS `open`, Linux `xdg-open`), `modifier_label()` |
| `src/localtranscriber/ui/main_window.py` | вместо `os.startfile` — `open_in_file_manager`; подписи `Ctrl`/`Cmd`; на macOS дополнительно `<Command-o>`, `<Command-s>` |
| `scripts/run.sh`, `scripts/build_mac.sh` (новые) | запуск и сборка `.app` + ad-hoc подпись + `.zip` |
| `.github/workflows/build-macos.yml` (новый) | `macos-14`, Python 3.13, тесты/линт/типы, сборка, артефакт |
| `README.md`, `HANDOFF.md` | раздел про macOS |

Обратная совместимость: на Windows ветки кода не меняются, добавляются только
платформенные проверки; тесты фиксируют оба поведения.

## 3. Декомпозиция работ

| ID | Задание | Агент | Зависит от | Оценка | Файлы |
|---|---|---|---|---|---|
| DEV-01 | Платформенные каталоги + тесты | developer | — | 40 мин | `config.py`, `tests/test_platform_paths.py` |
| DEV-02 | Открытие папки и горячие клавиши + тесты | developer | DEV-01 | 40 мин | `platform_utils.py`, `ui/main_window.py`, `tests/test_platform_utils.py` |
| DEV-03 | `run.sh`, `build_mac.sh` | developer | DEV-01 | 30 мин | `scripts/*.sh` |
| DEV-04 | GitHub Actions workflow | developer | DEV-03 | 30 мин | `.github/workflows/build-macos.yml` |
| DEV-05 | Документация, проверка на Windows | developer | DEV-01…DEV-04 | 30 мин | `README.md`, `HANDOFF.md` |

## 4. Этапы

| Этап | Результат | Критерий завершения |
|---|---|---|
| Разработка | порт + скрипты + CI | `pytest`, `ruff`, `mypy` зелёные на Windows |
| Проверка | preflight колёс под macOS, ревью workflow | все пакеты имеют wheel под cp313/arm64 |
| Интеграция | зелёный workflow, скачанный `.app` | артефакт запускается на Mac |

## 5. План проверки

- Сборка: `.\.venv\Scripts\python.exe -m PyInstaller …` (Windows) — без регрессии; `build_mac.sh` — в CI.
- Линтер: `ruff check .`
- Типы: `mypy src`
- Тесты: `pytest -o addopts="" -q`
- Ревью: самопроверка developer (независимые tester/reviewer недоступны — лимит субагентов, как в TASK-0001)
- Безопасность: секретов в репозитории нет, workflow использует только `GITHUB_TOKEN` по умолчанию
- Ручная проверка: запуск `.app` на Mac (заказчик/знакомый/облако)

## 6. Риски и меры

| Риск | Мера |
|---|---|
| Нет wheel под macOS arm64 | предварительный `pip download --platform macosx_11_0_arm64 --python-version 3.13 --only-binary=:all:` |
| PyInstaller теряет данные пакетов | `--collect-all` как на Windows + `--selftest` |
| Gatekeeper | ad-hoc подпись, инструкция в README |
| Пуш в GitHub | выполняется только после явного разрешения заказчика |

## 7. Согласование

| Поле | Значение |
|---|---|
| Decision | approved |
| Approved by | Сергей |
| Approval date | 2026-11-13T20:14:24+03:00 |
| Comment | Вариант 1: сборка под macOS через GitHub Actions |

> `Decision` должен быть изменён на `approved` только человеком.
