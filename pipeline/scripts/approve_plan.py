#!/usr/bin/env python3
"""Approve or reject a task plan. Intended to be run by a human."""

import argparse
import json
import sys
from datetime import datetime

import common as pipe


def main():
    pipe.setup_console()
    parser = argparse.ArgumentParser(description="Approve or reject a task plan")
    parser.add_argument("--task", required=True, help="Task ID, e.g. TASK-0001")
    parser.add_argument("--project", help="Project directory (optional if registered)")
    parser.add_argument("--by", required=True, help="Full name of the approver")
    parser.add_argument("--comment", default="", help="Approval comment")
    parser.add_argument("--reject", action="store_true", help="Reject the plan")
    args = parser.parse_args()

    project_root, task_dir = pipe.find_task(args.task, args.project)
    if not task_dir:
        print(f"ERROR: task {args.task} not found", file=sys.stderr)
        if project_root:
            print(f"Checked: {pipe.project_tasks_dir(project_root)}", file=sys.stderr)
        else:
            print("Specify --project or create the task with new_task.py", file=sys.stderr)
        return 2

    plan_path = task_dir / "02-plan.md"
    status_path = task_dir / "status.json"
    if not plan_path.exists():
        print(f"ERROR: {plan_path} not found", file=sys.stderr)
        return 2
    if not status_path.exists():
        print(f"ERROR: {status_path} not found", file=sys.stderr)
        return 2

    decision = "rejected" if args.reject else "approved"
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    text = plan_path.read_text(encoding="utf-8-sig")
    text = pipe.update_table_value(text, "Decision", decision)
    text = pipe.update_table_value(text, "Approved by", args.by.strip())
    text = pipe.update_table_value(text, "Approval date", now)
    text = pipe.update_table_value(text, "Comment", args.comment.strip())
    plan_path.write_text(text, encoding="utf-8")

    status = json.loads(status_path.read_text(encoding="utf-8-sig"))
    status["approval"] = {
        "plan": decision,
        "by": args.by.strip(),
        "date": now,
        "comment": args.comment.strip(),
    }
    status["stage"] = "analysis" if args.reject else "plan_approved"
    status["updated"] = now
    status["project_root"] = str(project_root)
    status_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with (task_dir / "log.md").open("a", encoding="utf-8") as log:
        log.write(
            f"- {now} — план {decision}: {args.by.strip()}. "
            f"Комментарий: {args.comment.strip() or '—'}\n"
        )

    print(f"Plan {decision}: {args.task}")
    print(f"Approver: {args.by.strip()}")
    print(f"Project: {project_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
