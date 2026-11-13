#!/usr/bin/env python3
"""Initialize a project directory for the AI development pipeline."""

import argparse
import json
import re
import shutil

import common as pipe

TOOLKIT_ROOT = pipe.SCRIPT_ROOT

AGENTS_TEMPLATE = """# AI Development Pipeline

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
"""


def copy_files(src_dir, dst_dir, force, pattern="*"):
    copied = []
    skipped = []
    if not src_dir.is_dir():
        return copied, skipped
    for src in sorted(src_dir.rglob(pattern)):
        if src.is_dir() or "__pycache__" in src.parts:
            continue
        dst = dst_dir / src.relative_to(src_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and not force:
            skipped.append(str(dst))
            continue
        shutil.copy2(src, dst)
        copied.append(str(dst))
    return copied, skipped


def write_if_missing(path, content, force):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def safe_name(name):
    cleaned = re.sub(r"[^\w.-]+", "-", name.strip(), flags=re.UNICODE).strip("-._")
    return cleaned or "project"


def apply_stack(config_path, stack, force):
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            config = {}
    if stack:
        if config.get("default_stack") and not force:
            return False
        config["default_stack"] = stack
    config.setdefault("max_iterations", 3)
    config.setdefault("branch_prefix", "pipeline/")
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def main():
    pipe.setup_console()
    parser = argparse.ArgumentParser(description="Initialize a project for the pipeline")
    parser.add_argument("--path", help="Project directory (created if missing)")
    parser.add_argument("--name", help="Project name; used for registry and default path")
    parser.add_argument("--stack", default="", help="Default stack description")
    parser.add_argument("--force", action="store_true", help="Overwrite existing pipeline files")
    parser.add_argument("--minimal", action="store_true", help="Do not copy agents, commands and AGENTS.md")
    args = parser.parse_args()

    if args.path:
        project_root = pipe.as_path(args.path)
        name = (args.name or project_root.name).strip()
    elif args.name:
        name = args.name.strip()
        project_root = (TOOLKIT_ROOT / "projects" / safe_name(name)).resolve()
    else:
        parser.error("укажите --path или --name")

    project_root.mkdir(parents=True, exist_ok=True)

    if project_root == TOOLKIT_ROOT:
        pipe.ensure_task_layout(project_root)
        pipe.register_project(project_root, TOOLKIT_ROOT, name)
        print(f"Project: {project_root}")
        print("This is already the pipeline root; task layout ensured.")
        return 0

    copied = []
    skipped = []

    # Pipeline folder: scripts, templates, config, task directories.
    for sub in ("scripts", "templates"):
        c, s = copy_files(TOOLKIT_ROOT / "pipeline" / sub, project_root / "pipeline" / sub, args.force)
        copied += c
        skipped += s

    config_src = TOOLKIT_ROOT / "pipeline" / "config.json"
    config_dst = project_root / "pipeline" / "config.json"
    if config_src.exists() and (args.force or not config_dst.exists()):
        shutil.copy2(config_src, config_dst)
        copied.append(str(config_dst))
    elif config_dst.exists():
        skipped.append(str(config_dst))
    apply_stack(config_dst, args.stack, args.force)

    pipe.ensure_task_layout(project_root)

    docs = TOOLKIT_ROOT / "pipeline" / "PIPELINE.md"
    if docs.exists():
        dst = project_root / "pipeline" / "PIPELINE.md"
        if args.force or not dst.exists():
            shutil.copy2(docs, dst)
            copied.append(str(dst))
        else:
            skipped.append(str(dst))

    if not args.minimal:
        c, s = copy_files(
            TOOLKIT_ROOT / ".opencode" / "agents",
            project_root / ".opencode" / "agents",
            args.force,
        )
        copied += c
        skipped += s
        c, s = copy_files(
            TOOLKIT_ROOT / ".opencode" / "commands",
            project_root / ".opencode" / "commands",
            args.force,
        )
        copied += c
        skipped += s
        if write_if_missing(project_root / "AGENTS.md", AGENTS_TEMPLATE, args.force):
            copied.append(str(project_root / "AGENTS.md"))
        else:
            skipped.append(str(project_root / "AGENTS.md"))

    entry = pipe.register_project(project_root, TOOLKIT_ROOT, name)

    print(f"Project: {project_root}")
    print(f"Name: {entry['name']}")
    print(f"Registered in: {pipe.registry_path(TOOLKIT_ROOT)}")
    print(f"Copied files: {len(copied)}")
    print(f"Skipped existing files: {len(skipped)}")
    if skipped:
        print("Use --force to overwrite skipped files.")
    print()
    print("Next:")
    print(f'  python "{project_root / "pipeline" / "scripts" / "new_task.py"}" --project "{project_root}" --title "..." --mode improvement')
    print("  or run /pipeline-start inside OpenCode.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
