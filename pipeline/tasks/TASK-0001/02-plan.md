# План работ: TASK-0001

## 1. Краткое резюме

Создаём локальное настольное приложение **LocalTranscriber** на Python 3.14 + Tkinter, которое одним окном закрывает два сценария: речь → текст (faster-whisper, CPU int8, без ffmpeg — через PyAV) и изображение/PDF → текст (RapidOCR на ONNX Runtime + PyMuPDF для текстового слоя). Всё выполняется в фоновом потоке с прогрессом и отменой, результат редактируется и сохраняется в `.txt` (все типы) или `.srt`/`.vtt`/`.json` (аудио/видео). Сеть нужна только для однократной загрузки моделей; приложение работает офлайн.

Техническая выполнимость на текущем окружении проверена заранее: для Python 3.14 существуют колёса `ctranslate2 4.9.0 (cp314)`, `av (cp312-abi3)`, `rapidocr 3.10.0 (py3)`, `sherpa-onnx (cp314)`; `onnxruntime`, `opencv`, `numpy`, `pymupdf`, `pillow` уже установлены; в RapidOCR есть модель распознавания `cyrillic_PP-OCRv5_rec_mobile` (русский). Ни `ffmpeg`, ни `tesseract` в системе нет — и они не нужны.

## 2. Технический подход

### 2.1. Стек и каркас (greenfield)

- **Язык**: Python 3.14 (единственная версия в системе), виртуальное окружение `.venv` в корне проекта.
- **GUI**: Tkinter + `ttk` (входит в Python, ничего не скачивать). Drag&drop — `tkinterdnd2`, подключается опционально (`try/except ImportError`), без него работает кнопка выбора файлов.
- **Речь**: `faster-whisper 1.2.x` → `ctranslate2`, `compute_type="int8"`, `cpu_threads` = число физических ядер (по умолчанию 16, настраивается), VAD `silero` включён (режет тишину, ускоряет длинные записи).
- **Медиа**: `av` (PyAV) — декодирование в 16 кГц моно float32 без внешнего ffmpeg, включая видео (берётся первая звуковая дорожка).
- **OCR**: `rapidocr 3.10` (ONNX Runtime, CPU), модель `cyrillic_PP-OCRv5_rec_mobile`; альтернатива `ch`/`latin` не требуется.
- **PDF**: `pymupdf` — `page.get_text()` для текстового слоя, `page.get_pixmap(dpi=300)` для страниц-сканов.
- **Тесты**: `pytest` (+ маркер `slow` для тестов с моделями), **линт**: `ruff`.

### 2.2. Архитектура

```text
UI (Tkinter, главный поток)
  └─ JobQueue (jobs.py): очередь + worker-поток + queue.Queue событий
        └─ router.route(path) -> engine
              ├─ WhisperEngine(audio.py + engines/whisper_engine.py)  -> segments[(start, end, text)]
              ├─ OcrEngine(engines/ocr_engine.py)                     -> lines[] -> text
              └─ PdfPipeline(pdf.py)                                  -> pages[] (text | ocr)
        └─ textformat.py: segments -> абзацы / srt / vtt / json, сохранение
```

- **Потоки**: один worker-поток на очередь, обмен событиями (`progress`, `partial`, `done`, `error`) через `queue.Queue`; UI опрашивает очередь через `after(100)`. Отмена — `threading.Event`, движки проверяют его между сегментами/страницами.
- **Ленивая инициализация**: движки создаются при первом задании в worker-потоке; статус «Загрузка движка…» в UI. Это снимает R-06.
- **Единый интерфейс движка** (`engines/base.py`): `transcribe(path, options, progress_cb, cancel_event) -> Result(text, segments|pages, language, duration)`. Это позволяет позже добавить GigaAM/Vosk без изменения UI.
- **Пути**: модели — `%LOCALAPPDATA%\LocalTranscriber\models` (`download_root` для faster-whisper, `model_dir` для RapidOCR); настройки — `%APPDATA%\LocalTranscriber\settings.json`; логи — `%LOCALAPPDATA%\LocalTranscriber\logs\app.log` (RotatingFileHandler 5×2 МБ); результаты по умолчанию — `<Документы>\LocalTranscriber`.
- **Первый запуск** (`models_setup.py`): проверка наличия файлов моделей → окно с прогрессом загрузки (`huggingface_hub` для Whisper, HTTP-загрузка с ModelScope и резервным HF-зеркалом для OCR) → при ошибке сети понятное сообщение и кнопка «Повторить».
- **Ошибки**: доменные исключения `LocalTranscriberError` с человекочитаемым текстом; traceback только в лог.

### 2.3. Затрагиваемые модули

Проект новый; создаются файлы из раздела 0 спецификации. Внешние системы не затрагиваются. Конвейер проекта (`pipeline/`) не изменяется, кроме артефактов задачи.

### 2.4. Обратная совместимость

Нет существующего кода — регрессия ограничена рамками проекта. Закрепляем версии зависимостей в `requirements.txt`, чтобы сборка была воспроизводимой.

## 3. Декомпозиция работ

| ID | Задание | Агент | Зависит от | Оценка | Файлы |
|---|---|---|---|---|---|
| DEV-01 | Каркас проекта: `pyproject.toml`, `requirements.txt`, конфиг и настройки, логирование, `textformat.py`, `router.py`, `run.ps1`, каркас тестов и README | developer | — | 3 ч | `pyproject.toml`, `requirements.txt`, `run.ps1`, `src/localtranscriber/{__init__,__main__,config,logging_setup,router,textformat}.py`, `tests/{test_config,test_textformat,test_router}.py` |
| DEV-02 | Движок речи: декодирование PyAV, интеграция faster-whisper (int8, VAD, cpu_threads), сегменты и таймкоды, отмена, оценка длительности | developer | DEV-01 | 5 ч | `src/localtranscriber/audio.py`, `src/localtranscriber/engines/{base,whisper_engine}.py`, `tests/test_whisper_engine.py` |
| DEV-03 | OCR и PDF: RapidOCR с русской моделью, сборка строк в порядке чтения, PyMuPDF (текстовый слой / рендер 300 DPI), постраничная склейка | developer | DEV-01 | 5 ч | `src/localtranscriber/pdf.py`, `src/localtranscriber/engines/ocr_engine.py`, `tests/{test_ocr_engine,test_pdf}.py` |
| DEV-04 | GUI и очередь: окно, drag&drop, список файлов, прогресс по файлу и общий, отмена, редактор результата, копирование, сохранение в txt/srt/vtt/json, окно настроек | developer | DEV-02, DEV-03 | 6 ч | `src/localtranscriber/app.py`, `src/localtranscriber/jobs.py`, `src/localtranscriber/ui/{main_window,widgets}.py`, `tests/test_jobs.py` |
| DEV-05 | Первый запуск и приёмка: `models_setup.py` (скачивание моделей, прогресс, офлайн-ошибки), бенчмарк на реальных файлах, README (установка, офлайн-режим, советы по качеству), проверка FR-12/FR-14/FR-15 | developer | DEV-04 | 3 ч | `src/localtranscriber/models_setup.py`, `README.md`, `scripts/benchmark.py`, `testdata/` (короткие сэмплы) |

Итого: ≈22 ч работы разработчика, 5 атомарных заданий с последовательными зависимостями; DEV-02 и DEV-03 могут выполняться параллельно после DEV-01.

## 4. Этапы

| Этап | Результат | Критерий завершения |
|---|---|---|
| Разработка | Работающее приложение, тесты, README | Все задания DEV-01…DEV-05 закрыты отчётами, `pytest -q` и `ruff check .` зелёные |
| Проверка | Независимые тест-репорт и ревью | Tester: PASS по сценариям раздела 8 спецификации; Reviewer: APPROVE по коду и архитектуре |
| Интеграция | Собранное окружение `.venv`, прогон демо-набора файлов | Регрессия пройдена, бенчмарк зафиксирован |
| Приёмка | `06-acceptance.md` | Человек подтверждает: обработаны реальные аудио, PDF и фото |

## 5. План проверки

- **Сборка**: `python -m compileall -q src` и создание venv из `requirements.txt`.
- **Линтер**: `python -m ruff check .`
- **Типы**: `python -m mypy src` с `ignore_missing_imports` для `faster_whisper`, `av`, `rapidocr` (проверка собственного кода, не сторонних библиотек).
- **Тесты**: `python -m pytest -q` (быстрые), `python -m pytest -q -m slow` (с моделями, вручную).
- **Ревью**: отдельный субагент-ревьюер проверяет архитектуру, обработку ошибок, потоки, утечки ресурсов, соответствие спецификации.
- **Безопасность**: риск `normal` — обязательный отчёт не требуется; в рамках ревью проверяется отсутствие сетевых вызовов при обработке, отсутствие секретов, безопасная работа с путями.
- **Ручная проверка**: сценарии 1–5 из раздела 8 спецификации на реальных файлах заказчика (аудио, скан PDF, фото документа).
- **Бенчмарк**: замер скорости для `medium` и `large-v3` на 10-минутной записи, результат — в README и отчёте DEV-05.

## 6. Риски и меры

| Риск | Мера |
|---|---|
| Скорость `large-v3` на CPU ниже ожидаемой | По умолчанию `medium`; выбор модели в настройках; VAD и `int8`; честная оценка времени в UI; бенчмарк в DEV-05 |
| Модель `cyrillic` RapidOCR недоступна на ModelScope | Резервное HF-зеркало, кэш моделей в `%LOCALAPPDATA%`, понятная ошибка и повтор загрузки |
| Качество OCR на плохих сканах | Ручное редактирование результата, предупреждение о низкой уверенности, рекомендации в README |
| Долгая первичная установка зависимостей и моделей | Прогресс в `run.ps1` и в окне загрузки моделей, предупреждение в README |
| Блокировка UI тяжёлыми импортами | Ленивая инициализация движков в worker-потоке, статус загрузки |
| Расхождение поведения PyAV на редких кодеках | Явная ошибка «не удалось декодировать звук», файл пропускается, очередь продолжается |
| Расползание scope (диаризация, exe, микрофон) | Явно вынесено в «не входит в scope»; изменения только по согласованию |

## 7. Согласование

| Поле | Значение |
|---|---|
| Decision | approved |
| Approved by |  Сергей|
| Approval date |  2026-11-13T12:00:25+03:00|
| Comment |  Согласовано, начинаем MVP|

> `Decision` должен быть изменён на `approved` только человеком.
