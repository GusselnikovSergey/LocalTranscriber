# История задачи TASK-0002

- 2026-11-13T20:12:00+03:00 — задача создана (`new_task.py`), режим improvement:
  сборка под macOS через GitHub Actions.
- 2026-11-13T20:15:00+03:00 — спецификация и план написаны; план утверждён
  (`approve_plan.py --by "Сергей"`), шлюз `plan` — PASS. Основание: заказчик выбрал
  вариант «GitHub Actions» (сообщения «давай 1 вариант», «собираем пока под мак»).
- 2026-11-13T20:20:00+03:00 — реализован порт: `platform_utils.py`, платформенные пути
  в `config.py`, `Cmd`-клавиши, `run.sh`, `build_mac.sh`, workflow, `--diagnose` в
  launcher. Тесты: 106 passed / 1 skipped, ruff и mypy чистые.
- 2026-11-13T20:25:00+03:00 — preflight колёс: все зависимости имеют wheel под
  `macosx_14_0_arm64` / cp313 (включая `av==19.0.2`; при теге `macosx_11_0` pip даёт
  ложный минус). Windows-регрессия: `build_exe.ps1` + `--selftest` — OK,
  `gui_smoke.py` — OK, `--diagnose` внутри exe — OK.
- 2026-11-13T20:30:00+03:00 — ожидание: репозиторий GitHub и разрешение на push.
  Получена ссылка https://github.com/GusselnikovSergey/LocalTranscriber — ветка `main` и
  тег `v0.1.0` запушены, workflow запустился.
- 2026-11-13T20:37:00+03:00 — первый прогон отменён GitHub: «The configuration
  'macos-14-arm64-us-default' is not supported» (macOS 14 в Actions снят с поддержки
  02.11.2026). `runs-on` изменён на `macos-15` (arm64 GA), тег `v0.1.1` — повторный запуск.
