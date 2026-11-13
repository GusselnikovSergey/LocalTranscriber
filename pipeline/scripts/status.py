#!/usr/bin/env python3
"""Show pipeline task status and missing artifacts."""

import argparse
import sys

import common as pipe

ARTIFACTS = (
    "00-task.md",
    "01-spec.md",
    "02-plan.md",
    "03-assignments",
    "04-development",
    "05-verification/checks.log",
    "05-verification/test-report.md",
    "05-verification/review-report.md",
    "05-verification/security-report.md",
    "06-acceptance.md",
)

NEXT_ACTION = {
    "intake": "Заполнить 00-task.md и запустить анализ (/pipeline-plan)",
    "analysis": "Завершить анализ и план (/pipeline-plan)",
    "plan_pending": "Утвердить план человеком (approve_plan.py)",
    "plan_approved": "Запустить разработку (/pipeline-build)",
    "development": "Завершить разработку и запустить проверки (/pipeline-verify)",
    "verification": "Завершить проверку и принять решение",
    "rework": "Устранить дефекты и повторить проверку (/pipeline-rework)",
    "accepted": "Оформить приёмку (/pipeline-accept)",
    "done": "Задача закрыта",
}


def show_task(task_id, project=None):
    project_root, task_dir = pipe.find_task(task_id, project)
    if not task_dir:
        print(f"ERROR: task not found: {task_id}", file=sys.stderr)
        if project_root:
            print(f"Checked: {pipe.project_tasks_dir(project_root)}", file=sys.stderr)
        else:
            print("Specify --project or create the task first", file=sys.stderr)
        return 2

    status = pipe.load_status(task_dir)
    if not status:
        print(f"WARNING: status.json is missing or invalid in {task_dir}")

    mode = status.get("mode", "—")
    print(f"Task: {task_id}")
    print(f"Title: {status.get('title', '—')}")
    print(f"Project: {status.get('project_name', project_root.name)}")
    print(f"Project root: {project_root}")
    print(f"Mode: {mode}")
    print(f"Stack: {status.get('stack', '—')}")
    print(f"Stage: {status.get('stage', '—')}")
    print(f"Verdict: {status.get('verdict', '—')}")
    print(f"Risk: {status.get('risk', '—')}")
    print(f"Iterations: {status.get('iterations', 0)} / {status.get('max_iterations', '—')}")
    print(f"Updated: {status.get('updated', '—')}")
    print()
    print("Artifacts:")
    for rel in ARTIFACTS:
        path = task_dir / rel
        mark = "x" if path.exists() else " "
        print(f"  [{mark}] {rel}")
    print()
    print(f"Next action: {NEXT_ACTION.get(status.get('stage', ''), 'Проверить артефакты и статус')}")
    return 0


def list_tasks(project=None):
    if project:
        roots = [pipe.resolve_project(project)]
        pairs = []
        for root in roots:
            tasks_dir = pipe.project_tasks_dir(root)
            if not tasks_dir.exists():
                continue
            for path in sorted(tasks_dir.iterdir()):
                if path.is_dir() and pipe.TASK_RE.fullmatch(path.name):
                    pairs.append((root, path))
    else:
        pairs = pipe.all_tasks()

    if not pairs:
        print("No tasks yet. Create a task with /pipeline-start.")
        return 0

    print(f"{'ID':<12} {'Project':<20} {'Mode':<12} {'Stage':<14} {'Iter':<5} {'Verdict':<10} Title")
    print("-" * 110)
    for root, task_dir in pairs:
        status = pipe.load_status(task_dir)
        project_name = str(status.get("project_name") or root.name)
        title = str(status.get("title", "—"))
        if len(title) > 34:
            title = title[:31] + "..."
        print(
            f"{task_dir.name:<12} "
            f"{project_name[:20]:<20} "
            f"{str(status.get('mode', '—')):<12} "
            f"{str(status.get('stage', '—')):<14} "
            f"{str(status.get('iterations', 0)):<5} "
            f"{str(status.get('verdict', '—')):<10} "
            f"{title}"
        )
    return 0


def main():
    pipe.setup_console()
    parser = argparse.ArgumentParser(description="Show pipeline task status")
    parser.add_argument("--task", help="Task ID, e.g. TASK-0001")
    parser.add_argument("--project", help="Project directory (optional if registered)")
    args = parser.parse_args()
    if args.task:
        return show_task(args.task, args.project)
    return list_tasks(args.project)


if __name__ == "__main__":
    raise SystemExit(main())
