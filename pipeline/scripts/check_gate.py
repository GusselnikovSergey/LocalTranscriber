#!/usr/bin/env python3
"""Validate a pipeline gate before moving to the next stage."""

import argparse
import re
from pathlib import Path

import common as pipe

GATES = ("intake", "analysis", "plan", "development", "verification", "acceptance")


def check_intake(task_dir, status):
    errors = []
    task = pipe.read_text(task_dir / "00-task.md")
    if not task:
        return ["00-task.md не найден"]
    if "<!-- Вставьте исходный текст" in task:
        errors.append("00-task.md: не заполнен исходный текст задачи")
    if "## Исходная задача / ТЗ" not in task:
        errors.append("00-task.md: нет раздела 'Исходная задача / ТЗ'")
    if len(task.strip()) < 200:
        errors.append("00-task.md: слишком мало содержимого")

    project_root = str(status.get("project_root", "")).strip()
    if not project_root:
        errors.append("status.json: не указан project_root")
    elif not Path(project_root).is_dir():
        errors.append(f"status.json: каталог проекта не найден: {project_root}")

    mode = pipe.normalize_mode(status.get("mode"))
    if mode not in pipe.MODES:
        errors.append(f"status.json: mode = '{mode}', требуется greenfield или improvement")

    stack = str(status.get("stack", "")).strip()
    if not stack or stack.lower() in ("auto", "tbd"):
        errors.append("status.json: не определён стек проекта (stack)")
    return errors


def check_analysis(task_dir, status):
    errors = []
    spec = pipe.read_text(task_dir / "01-spec.md")
    plan = pipe.read_text(task_dir / "02-plan.md")
    if not spec:
        errors.append("01-spec.md не найден")
    if not plan:
        errors.append("02-plan.md не найден")
    if spec and "{{" in spec:
        errors.append("01-spec.md: остались незаполненные placeholders")
    if plan and "{{" in plan:
        errors.append("02-plan.md: остались незаполненные placeholders")
    if spec and "<!-- Что должно измениться" in spec:
        errors.append("01-spec.md: не заполнена цель")
    if plan and "<!-- Подход к решению" in plan:
        errors.append("02-plan.md: не заполнен подход")
    if spec and "## 10. Definition of Ready" not in spec:
        errors.append("01-spec.md: нет раздела Definition of Ready")
    if spec and not re.search(r"- \[[xX]\]", spec):
        errors.append("01-spec.md: Definition of Ready не отмечен")

    # Project context must be concrete: mode and stack are not "auto".
    spec_mode = pipe.normalize_mode(pipe.table_value(spec, "Режим"))
    if spec_mode not in pipe.MODES:
        errors.append("01-spec.md: в контексте проекта не указан режим (greenfield/improvement)")
    spec_stack = pipe.table_value(spec, "Стек")
    if not spec_stack or spec_stack.lower() in ("auto", "tbd", "<...>"):
        errors.append("01-spec.md: в контексте проекта не указан стек")

    status_mode = pipe.normalize_mode(status.get("mode"))
    if spec_mode in pipe.MODES and status_mode in pipe.MODES and spec_mode != status_mode:
        errors.append(
            f"01-spec.md: режим '{spec_mode}' не совпадает с status.json '{status_mode}'"
        )

    spec_rows = []
    for line in spec.splitlines():
        s = line.strip()
        if not s.startswith("|") or not re.search(r"\|\s*FR-\d+\s*\|", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) >= 4:
            spec_rows.append(cells)
    if not any(c[1] and c[3] and not c[1].startswith("<") for c in spec_rows):
        errors.append("01-spec.md: нет заполненных требований FR-XX (описание и критерий приёмки)")

    plan_rows = []
    for line in plan.splitlines():
        s = line.strip()
        if not s.startswith("|") or not re.search(r"\|\s*DEV-\d+\s*\|", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) >= 6:
            plan_rows.append(cells)
    if not any(c[1] and c[5] and not c[1].startswith("<") for c in plan_rows):
        errors.append("02-plan.md: нет заполненных заданий DEV-XX (название и файлы)")
    if plan and "## 3. Декомпозиция" not in plan:
        errors.append("02-plan.md: нет раздела декомпозиции")
    return errors


def check_plan(task_dir, status):
    errors = []
    plan = pipe.read_text(task_dir / "02-plan.md")
    if not plan:
        return ["02-plan.md не найден"]
    decision = pipe.table_value(plan, "Decision") or pipe.line_value(plan, "Decision")
    approver = pipe.table_value(plan, "Approved by") or pipe.line_value(plan, "Approved by")
    if decision.lower() != "approved":
        errors.append(f"02-plan.md: Decision = '{decision or 'пусто'}', требуется 'approved'")
    if not approver:
        errors.append("02-plan.md: не указан Approved by")
    if status.get("approval", {}).get("plan") != "approved":
        errors.append("status.json: approval.plan не равен 'approved'")
    return errors


def check_development(task_dir):
    errors = []
    assignments = sorted((task_dir / "03-assignments").glob("DEV-*.md"))
    if not assignments:
        errors.append("03-assignments: нет заданий DEV-XX")
        return errors
    for assignment in assignments:
        text = pipe.read_text(assignment)
        if "{{" in text:
            errors.append(f"{assignment.name}: остались незаполненные placeholders")
        report = task_dir / "04-development" / f"{assignment.stem}-report.md"
        if not report.exists():
            errors.append(f"04-development/{report.name} не найден")
            continue
        report_text = pipe.read_text(report)
        if len(report_text.strip()) < 100:
            errors.append(f"04-development/{report.name}: отчёт слишком короткий")
        lowered = report_text.lower()
        if "заблокировано" in lowered or "blocked" in lowered:
            errors.append(f"04-development/{report.name}: задание заблокировано")
    return errors


def check_verification(task_dir, status, config):
    errors = []
    test_report = pipe.read_text(task_dir / "05-verification" / "test-report.md")
    review_report = pipe.read_text(task_dir / "05-verification" / "review-report.md")
    checks_log = task_dir / "05-verification" / "checks.log"

    if not test_report:
        errors.append("05-verification/test-report.md не найден")
    elif not pipe.has_verdict(test_report, "PASS"):
        errors.append("test-report.md: Verdict не PASS")
    if not review_report:
        errors.append("05-verification/review-report.md не найден")
    elif not pipe.has_verdict(review_report, "APPROVE"):
        errors.append("review-report.md: Verdict не APPROVE")
    if not checks_log.exists():
        errors.append("05-verification/checks.log не найден")

    risk = str(status.get("risk", "normal")).lower()
    security_required = risk in {
        str(x).lower() for x in config.get("security_required_for_risk", [])
    }
    if security_required:
        security_report = pipe.read_text(task_dir / "05-verification" / "security-report.md")
        if not security_report:
            errors.append("05-verification/security-report.md не найден (требуется для high-risk)")
        elif not pipe.has_verdict(security_report, "PASS"):
            errors.append("security-report.md: Verdict не PASS")
    return errors


def check_acceptance(task_dir, status):
    errors = []
    acceptance = pipe.read_text(task_dir / "06-acceptance.md")
    if not acceptance:
        return ["06-acceptance.md не найден"]
    decision = pipe.line_value(acceptance, "Decision")
    if decision not in ("ACCEPTED", "ACCEPTED WITH NOTES"):
        errors.append(f"06-acceptance.md: Decision = '{decision or 'пусто'}', требуется ACCEPTED")
    accepted_by = pipe.table_value(acceptance, "ФИО")
    if not accepted_by or accepted_by.startswith("<"):
        errors.append("06-acceptance.md: не указано ФИО принявшего")
    if status.get("stage") != "done":
        errors.append(f"status.json: stage = '{status.get('stage')}', требуется 'done'")
    return errors


def main():
    pipe.setup_console()
    parser = argparse.ArgumentParser(description="Validate a pipeline gate")
    parser.add_argument("--task", required=True, help="Task ID, e.g. TASK-0001")
    parser.add_argument("--gate", required=True, choices=GATES, help="Gate to validate")
    parser.add_argument("--project", help="Project directory (optional if registered)")
    args = parser.parse_args()

    project_root, task_dir = pipe.find_task(args.task, args.project)
    if not task_dir:
        print(f"FAIL: gate '{args.gate}' for {args.task}")
        if project_root:
            print(f" - папка задачи не найдена: {pipe.project_tasks_dir(project_root) / args.task}")
        else:
            print(f" - задача {args.task} не найдена; укажите --project")
        return 1

    status = pipe.load_status(task_dir)
    config = pipe.load_config(project_root)

    if args.gate == "intake":
        errors = check_intake(task_dir, status)
    elif args.gate == "analysis":
        errors = check_analysis(task_dir, status)
    elif args.gate == "plan":
        errors = check_plan(task_dir, status)
    elif args.gate == "development":
        errors = check_development(task_dir)
    elif args.gate == "verification":
        errors = check_verification(task_dir, status, config)
    else:
        errors = check_acceptance(task_dir, status)

    if errors:
        print(f"FAIL: gate '{args.gate}' for {args.task}")
        for error in errors:
            print(f" - {error}")
        return 1

    print(f"PASS: gate '{args.gate}' for {args.task}")
    print(f"Project: {project_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
