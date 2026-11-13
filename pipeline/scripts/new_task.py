#!/usr/bin/env python3
"""Create a new pipeline task from templates."""

import argparse
import json
import sys
from datetime import datetime

import common as pipe


def main():
    pipe.setup_console()
    parser = argparse.ArgumentParser(description="Create a new pipeline task")
    parser.add_argument("--title", required=True, help="Short task title")
    parser.add_argument("--id", help="Explicit task ID, e.g. TASK-0001")
    parser.add_argument("--project", help="Project directory; defaults to the pipeline root")
    parser.add_argument("--priority", default="medium", help="low|medium|high|critical")
    parser.add_argument("--type", default="feature", help="feature|bug|integration|refactor|docs|migration")
    parser.add_argument("--risk", default="normal", help="normal|high|security|data")
    parser.add_argument("--mode", default="improvement", choices=("greenfield", "improvement"),
                        help="greenfield = с нуля, improvement = доработка")
    parser.add_argument("--stack", default="", help="Technology stack, e.g. 'Node.js + React'")
    parser.add_argument("--repo", default="", help="Repository URL or path")
    parser.add_argument("--baseline", default="", help="Baseline branch or commit for improvement tasks")
    parser.add_argument("--customer", default="", help="Customer or responsible person")
    parser.add_argument("--source", default="", help="Source of the request")
    args = parser.parse_args()

    title = args.title.strip()
    if not title:
        print("ERROR: --title must not be empty", file=sys.stderr)
        return 2

    project_root = pipe.resolve_project(args.project)
    if args.project and not project_root.is_dir():
        print(f"ERROR: project directory not found: {project_root}", file=sys.stderr)
        print("Create it first or run init_project.py --path ...", file=sys.stderr)
        return 2

    project_templates = project_root / "pipeline" / "templates"
    templates_dir = project_templates if project_templates.is_dir() else pipe.SCRIPT_ROOT / "pipeline" / "templates"

    task_id = (args.id or pipe.next_task_id(project_root)).strip()
    if not pipe.TASK_RE.fullmatch(task_id):
        print("ERROR: task ID must look like TASK-0001", file=sys.stderr)
        return 2

    task_dir = pipe.project_tasks_dir(project_root) / task_id
    if task_dir.exists():
        print(f"ERROR: {task_dir} already exists", file=sys.stderr)
        return 2

    pipe.ensure_task_layout(project_root)
    task_dir.mkdir(parents=True, exist_ok=True)

    config = pipe.load_config(project_root)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    stack = args.stack.strip() or str(config.get("default_stack", "")).strip() or "auto"
    values = {
        "TASK_ID": task_id,
        "TITLE": title,
        "DATE": now[:10],
        "PRIORITY": args.priority,
        "TYPE": args.type,
        "RISK": args.risk,
        "MODE": args.mode,
        "STACK": stack,
        "REPO": args.repo,
        "BASELINE": args.baseline,
        "CUSTOMER": args.customer,
        "SOURCE": args.source,
        "PROJECT_NAME": project_root.name,
        "PROJECT_ROOT": str(project_root),
    }

    copies = {
        "task.md": "00-task.md",
        "spec.md": "01-spec.md",
        "plan.md": "02-plan.md",
        "acceptance.md": "06-acceptance.md",
    }
    for source_name, target_name in copies.items():
        source = templates_dir / source_name
        if not source.exists():
            print(f"ERROR: missing template {source}", file=sys.stderr)
            return 2
        content = pipe.render(source.read_text(encoding="utf-8"), values)
        (task_dir / target_name).write_text(content, encoding="utf-8")

    status = {
        "id": task_id,
        "title": title,
        "stage": "intake",
        "created": now,
        "updated": now,
        "iterations": 0,
        "max_iterations": int(config.get("max_iterations", 3)),
        "priority": args.priority,
        "type": args.type,
        "risk": args.risk,
        "mode": args.mode,
        "stack": stack,
        "repo": args.repo,
        "baseline": args.baseline,
        "customer": args.customer,
        "project_root": str(project_root),
        "project_name": project_root.name,
        "verdict": "pending",
        "branch": "",
        "approval": {"plan": "pending", "by": "", "date": ""},
    }
    (task_dir / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_dir / "log.md").write_text(
        f"# Log: {task_id}\n\n- {now} — задача создана ({args.mode}).\n",
        encoding="utf-8",
    )

    pipe.register_project(project_root)

    print(task_id)
    print(task_dir)
    print(f"Project: {project_root}")
    print(f"Mode: {args.mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
