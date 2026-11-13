# Задание DEV-01: Каркас проекта, настройки, логирование, форматирование текста

## Контекст

| Поле | Значение |
|---|---|
| Задача | TASK-0001 |
| Спецификация | `01-spec.md` |
| План | `02-plan.md` |
| Ветка | — (локальный каталог) |
| Зависит от | — |

## Scope

### Файлы, которые можно менять

- `pyproject.toml`, `requirements.txt`, `run.ps1`, `.gitignore`
- `src/localtranscriber/__init__.py`, `__main__.py`, `config.py`, `logging_setup.py`, `router.py`, `textformat.py`
- `tests/test_config.py`, `tests/test_textformat.py`, `tests/test_router.py`

### Файлы, которые нельзя менять

- `opencode.jsonc`
- `.opencode/**`
- `pipeline/config.json`
- `pipeline/scripts/**`
- `pipeline/templates/**`

## Требования

- FR-01 (частично: список поддерживаемых расширений), FR-02, FR-08, FR-09, FR-11, FR-15.
- `config.py`: dataclass `Settings` (model_size, language, cpu_threads, output_dir, show_timestamps), пути `%APPDATA%\LocalTranscriber\settings.json`, `%LOCALAPPDATA%\LocalTranscriber\{models,logs}`, загрузка с дефолтами и сохранение.
- `logging_setup.py`: RotatingFileHandler 5×2 МБ в `%LOCALAPPDATA%\LocalTranscriber\logs\app.log`.
- `router.py`: определение типа файла по расширению (`speech` / `image` / `pdf`), исключение `UnsupportedFileError`.
- `textformat.py`: `Segment`, сборка абзацев по паузам, экспорт `txt` / `srt` / `vtt` / `json`, маркеры страниц PDF, безопасное имя файла.
- `run.ps1`: создание `.venv`, установка зависимостей, запуск `python -m localtranscriber`.
- Тесты: настройки (дефолты, сохранение/загрузка, битый JSON), форматирование (SRT/VTT/JSON, абзацы, страницы), маршрутизация.

## Критерии готовности

- [ ] Код реализован
- [ ] Тесты добавлены или обновлены
- [ ] Сборка проходит (`python -m compileall -q src`)
- [ ] Линтер проходит (`ruff check .`)
- [ ] Типы проверены (mypy)
- [ ] Отчёт `04-development/DEV-01-report.md` заполнен
