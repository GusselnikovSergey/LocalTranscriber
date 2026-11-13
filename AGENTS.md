# AI Development Pipeline

Этот проект подключён к конвейеру ИИ-разработки.

Перед началом любой задачи:

1. Прочитай `pipeline/PIPELINE.md`.
2. Используй агента `orchestrator` (`.opencode/agents/orchestrator.md`).
3. Пройди шлюзы: intake → analysis → plan approval → development → verification → acceptance.

Артефакты задач: `pipeline/tasks/<TASK-ID>/`.

Команды:

- `/pipeline-start <описание>`
- `/pipeline-plan <ID>`
- `/pipeline-build <ID>`
- `/pipeline-verify <ID>`
- `/pipeline-rework <ID>`
- `/pipeline-status <ID>`
- `/pipeline-accept <ID>`

Жёсткие правила:

- Без утверждённого человеком плана разработка не начинается.
- Без заключений tester и reviewer приёмка невозможна.
- Максимум 3 итерации доработки, затем эскалация человеку.
- Никакого `git push`, merge в защищённые ветки и деплоя в продуктив.
- Изменения только в рамках задачи.
