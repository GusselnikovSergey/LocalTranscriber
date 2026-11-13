# Приёмка: TASK-0002

Decision: PENDING (ожидает ручного теста `.app` на Mac)

## 1. Критерии приёмки

| Критерий | Результат | Доказательство |
|---|---|---|
| FR-01 пути macOS | PASS | `tests/test_platform_paths.py`, `config.py` |
| FR-02 открытие папки через `open` | PASS | `tests/test_platform_utils.py`, `platform_utils.py` |
| FR-03 `Cmd+O` / `Cmd+S` | PASS | `tests/test_platform_utils.py`, `ui/main_window.py` |
| FR-04 `run.sh` | PASS (статически) | `bash -n` = 0; запуск на Mac не проверялся |
| FR-05 `build_mac.sh` собирает `.app` и zip | PASS | шаг «Build .app» прогона `v0.1.7` |
| FR-06 Actions собирает и отдаёт артефакт | PASS | прогон 43483275683, артефакт 224 МБ |
| FR-07 нет регрессии на Windows | PASS | 106 passed / 1 skipped, ruff, mypy, `build_exe.ps1` + `--selftest`, `gui_smoke` |
| Ручной запуск `.app` на Mac | НЕ ПРОВЕРЕНО | нет Mac у команды разработки |

## 2. Проверенные артефакты

- [x] `01-spec.md`
- [x] `02-plan.md` с `Decision: approved`
- [x] `04-development/DEV-01-report.md`
- [ ] `05-verification/test-report.md` с `Verdict: PASS` — не создан (независимый tester недоступен)
- [ ] `05-verification/review-report.md` с `Verdict: APPROVE` — не создан (независимый reviewer недоступен)
- [x] `05-verification/self-check.md` (самопроверка разработчика)
- [x] Регрессия пройдена
- [x] Документация обновлена (`README.md`, `HANDOFF.md`)

## 3. Открытые вопросы и остаточные работы

| ID | Описание | Владелец | Срок |
|---|---|---|---|
| O-01 | Запустить `.app` на Mac: Gatekeeper («правый клик → Открыть»), скачивание модели, распознавание, экспорт, `Cmd+S` | заказчик | после получения сборки |
| O-02 | Нужна ли подпись Apple Developer ID и нотаризация | заказчик | по желанию |
| O-03 | Нужен ли `.dmg` и/или сборка под Intel (`macos-15-intel`) | заказчик | по желанию |
| O-04 | Независимая проверка tester + reviewer (лимит бесплатных моделей) | команда | после восстановления лимита |

## 4. Решение

Ожидает ручного теста заказчиком. Код и сборка готовы: прогон `v0.1.7` зелёный,
`.app` собран и лежит в артефактах GitHub Actions.

## 5. Принял

| Поле | Значение |
|---|---|
| ФИО |  |
| Должность |  |
| Дата |  |
| Подпись |  |
