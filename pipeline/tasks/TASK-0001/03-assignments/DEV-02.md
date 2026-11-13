# Задание DEV-02: Движок речи (PyAV + faster-whisper, CPU int8)

## Контекст

| Поле | Значение |
|---|---|
| Задача | TASK-0001 |
| Спецификация | `01-spec.md` |
| План | `02-plan.md` |
| Ветка | — (локальный каталог) |
| Зависит от | DEV-01 |

## Scope

### Файлы, которые можно менять

- `src/localtranscriber/audio.py`
- `src/localtranscriber/engines/__init__.py`, `base.py`, `whisper_engine.py`
- `tests/test_whisper_engine.py`

### Файлы, которые нельзя менять

- `opencode.jsonc`
- `.opencode/**`
- `pipeline/config.json`
- `pipeline/scripts/**`
- `pipeline/templates/**`

## Требования

- FR-03, FR-04, FR-14 (частично), NFR по памяти и производительности.
- `audio.py`: декодирование любого поддерживаемого контейнера в float32 mono 16 кГц без внешнего ffmpeg (PyAV), выбор первой звуковой дорожки, корректная ошибка при её отсутствии, длительность.
- `engines/base.py`: протокол движка, `Result`, колбэк прогресса, `CancelToken`.
- `engines/whisper_engine.py`: ленивая инициализация `faster_whisper.WhisperModel` (cpu, int8, cpu_threads, download_root), VAD `silero`, язык по умолчанию `ru`, `beam_size=5`, `condition_on_previous_text=False`, отмена между сегментами, прогресс по `segment.end / duration`.
- Тесты: юнит-тесты на разбор сегментов (без модели), `slow`-тест на коротком wav.

## Критерии готовности

- [ ] Код реализован
- [ ] Тесты добавлены или обновлены
- [ ] Сборка проходит
- [ ] Линтер проходит
- [ ] Отчёт `04-development/DEV-02-report.md` заполнен
