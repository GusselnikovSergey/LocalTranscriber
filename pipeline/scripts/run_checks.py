#!/usr/bin/env python3
"""Run configured build, lint, typecheck and test commands for a task."""

import argparse
import subprocess
import sys
from datetime import datetime

import common as pipe

CHECKS = ("build", "lint", "typecheck", "test")
MAX_OUTPUT = 200_000


def main():
    pipe.setup_console()
    parser = argparse.ArgumentParser(description="Run pipeline checks")
    parser.add_argument("--task", required=True, help="Task ID, e.g. TASK-0001")
    parser.add_argument("--project", help="Project directory (optional if registered)")
    parser.add_argument("--only", default="", help="Comma-separated checks: build,lint,typecheck,test")
    parser.add_argument("--timeout", type=int, default=1800, help="Timeout per command, seconds")
    args = parser.parse_args()

    project_root, task_dir = pipe.find_task(args.task, args.project)
    if not task_dir:
        print(f"ERROR: task not found: {args.task}", file=sys.stderr)
        if project_root:
            print(f"Checked: {pipe.project_tasks_dir(project_root)}", file=sys.stderr)
        else:
            print("Specify --project or create the task first", file=sys.stderr)
        return 2

    config = pipe.load_config(project_root)
    selected = {x.strip().lower() for x in args.only.split(",") if x.strip()} or set(CHECKS)
    unknown = selected - set(CHECKS)
    if unknown:
        print(f"ERROR: unknown checks: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    output_dir = task_dir / "05-verification"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "checks.log"
    started = datetime.now().astimezone().isoformat(timespec="seconds")

    lines = [
        f"# Checks: {args.task}",
        f"Started: {started}",
        f"Project root: {project_root}",
        "",
    ]
    failures = []
    configured = 0

    for name in CHECKS:
        if name not in selected:
            continue
        command = str(config.get(f"{name}_command", "")).strip()
        lines.append(f"## {name}")
        lines.append(f"Command: {command or '(not configured)'}")
        if not command:
            lines.append("Result: SKIP (not configured)")
            lines.append("")
            print(f"[SKIP] {name}: not configured")
            continue

        configured += 1
        print(f"[RUN ] {name}: {command}")
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=args.timeout,
            )
            result = "PASS" if completed.returncode == 0 else "FAIL"
            lines.append(f"Exit code: {completed.returncode}")
            lines.append(f"Result: {result}")
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            if len(stdout) > MAX_OUTPUT:
                stdout = stdout[:MAX_OUTPUT] + "\n... (truncated)\n"
            if len(stderr) > MAX_OUTPUT:
                stderr = stderr[:MAX_OUTPUT] + "\n... (truncated)\n"
            if stdout:
                lines.append("### stdout")
                lines.append(stdout.rstrip())
            if stderr:
                lines.append("### stderr")
                lines.append(stderr.rstrip())
            if completed.returncode != 0:
                failures.append(name)
                print(f"[FAIL] {name} (exit {completed.returncode})")
            else:
                print(f"[PASS] {name}")
        except subprocess.TimeoutExpired:
            lines.append(f"Result: FAIL (timeout {args.timeout}s)")
            failures.append(name)
            print(f"[FAIL] {name}: timeout {args.timeout}s")
        except Exception as exc:  # noqa: BLE001 - report any execution error
            lines.append(f"Result: FAIL ({type(exc).__name__}: {exc})")
            failures.append(name)
            print(f"[FAIL] {name}: {exc}")
        lines.append("")

    finished = datetime.now().astimezone().isoformat(timespec="seconds")
    lines.append(f"Finished: {finished}")
    lines.append(f"Summary: {'FAIL' if failures else 'PASS'}")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Log: {log_path}")
    print(f"Project: {project_root}")
    if not configured:
        print("WARNING: no commands configured in pipeline/config.json")
        return 0
    if failures:
        print(f"FAILED: {', '.join(failures)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
