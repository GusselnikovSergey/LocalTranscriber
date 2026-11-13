# Отчёт DEV-01: Каркас проекта, настройки, логирование, форматирование текста

## Что сделано

- Создан каркас пакета `localtranscriber` (`src`-layout) с установкой в editable-режиме.
- `pyproject.toml`: зависимости, скрипт `localtranscriber`, конфигурация pytest (`markers = slow`), ruff, mypy (`ignore_missing_imports`).
- `requirements.txt`: закреплённые основные и dev-зависимости, включая `truststore` для доверия системному хранилищу сертификатов Windows.
- `run.ps1`: создаёт `.venv` при первом запуске, ставит зависимости по маркеру `.deps-installed`, запускает `python -m localtranscriber`.
- `config.py`: `Settings` (модель, язык, потоки, папка результатов, таймкоды), нормализация значений, атомарное сохранение в `%APPDATA%\LocalTranscriber\settings.json`, устойчивое чтение битого JSON.
- `logging_setup.py`: `RotatingFileHandler` 5 × 2 МБ в `%LOCALAPPDATA%\LocalTranscriber\logs\app.log`.
- `router.py`: `JobKind` (`speech`/`image`/`pdf`), наборы расширений, `detect_kind`, фильтры для диалога выбора файлов.
- `textformat.py`: `Segment`, склейка абзацев по паузам, таймкоды, экспорт `txt`/`srt`/`vtt`/`json`, маркеры страниц PDF, безопасные имена файлов.
- `errors.py`, `cancellation.py`: доменные исключения и токен отмены, общий для движков и очереди.
- Тесты: `tests/test_config.py`, `tests/test_router.py`, `tests/test_textformat.py`.

## Изменённые файлы

`pyproject.toml`, `requirements.txt`, `run.ps1`, `.gitignore`,
`src/localtranscriber/{__init__,__main__,config,logging_setup,router,textformat,errors,cancellation}.py`,
`tests/{test_config,test_router,test_textformat}.py`.

## Как проверено

```text
python -m pytest -q          → 57 passed, 1 skipped (slow)
python -m ruff check .       → All checks passed!
python -m mypy src           → Success: no issues found
python -m compileall -q src  → OK
```

## Отклонения от задания

- Добавлен модуль `cancellation.py`, чтобы не дублировать токен отмены в движках и очереди.
- Стек уточнён: вместо Tesseract используется RapidOCR (в системе нет tesseract, а RapidOCR — чистый onnxruntime).
- Добавлен `truststore`: корпоративный антивирус подменяет TLS-сертификаты, без системного хранилища скачивание моделей падало с `CERTIFICATE_VERIFY_FAILED`.

## Риски

- Пути к настройкам зависят от переменных `APPDATA`/`LOCALAPPDATA`; если они пусты, используются каталоги домашней папки.
