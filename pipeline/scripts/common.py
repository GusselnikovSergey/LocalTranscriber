#!/usr/bin/env python3
"""Shared helpers for the development pipeline scripts."""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG = {
    "max_iterations": 3,
    "branch_prefix": "pipeline/",
    "build_command": "",
    "lint_command": "",
    "typecheck_command": "",
    "test_command": "",
    "required_checks": ["build", "lint", "test"],
    "security_required_for_risk": ["high", "security", "data"],
    "default_stack": "",
}

TASK_RE = re.compile(r"^TASK-\d{4,}$")
MODES = ("greenfield", "improvement")


def setup_console():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def as_path(raw, base=None):
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = Path(base or Path.cwd()) / path
    return path.resolve()


def resolve_project(explicit=None):
    raw = (explicit or os.environ.get("PIPELINE_PROJECT") or "").strip()
    if raw:
        return as_path(raw)
    return SCRIPT_ROOT


def load_config(project_root):
    config = dict(DEFAULT_CONFIG)
    config["required_checks"] = list(DEFAULT_CONFIG["required_checks"])
    config["security_required_for_risk"] = list(DEFAULT_CONFIG["security_required_for_risk"])

    # Cockpit config is the fallback; project config always wins.
    candidates = []
    if project_root != SCRIPT_ROOT:
        candidates.append(SCRIPT_ROOT / "pipeline" / "config.json")
    candidates.append(project_root / "pipeline" / "config.json")

    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARNING: cannot read {path}: {exc}", file=sys.stderr)
            continue
        if isinstance(data, dict):
            config.update(data)
    return config


def registry_path(toolkit_root=None):
    return (toolkit_root or SCRIPT_ROOT) / "pipeline" / "projects.json"


def read_registry(toolkit_root=None):
    path = registry_path(toolkit_root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    projects = data.get("projects", []) if isinstance(data, dict) else data
    return [item for item in projects if isinstance(item, dict)]


def write_registry(projects, toolkit_root=None):
    path = registry_path(toolkit_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"projects": projects}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def register_project(project_root, toolkit_root=None, name=None):
    toolkit_root = toolkit_root or SCRIPT_ROOT
    project_root = Path(project_root).resolve()
    projects = read_registry(toolkit_root)
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    for entry in projects:
        raw = str(entry.get("path", "")).strip()
        if not raw:
            continue
        try:
            same = Path(raw).resolve() == project_root
        except OSError:
            same = False
        if same:
            entry["name"] = name or entry.get("name") or project_root.name
            entry["path"] = str(project_root)
            entry["updated"] = now
            write_registry(projects, toolkit_root)
            return entry

    entry = {
        "name": name or project_root.name,
        "path": str(project_root),
        "created": now,
        "updated": now,
    }
    projects.append(entry)
    write_registry(projects, toolkit_root)
    return entry


def known_projects(toolkit_root=None):
    toolkit_root = toolkit_root or SCRIPT_ROOT
    roots = [toolkit_root]
    for entry in read_registry(toolkit_root):
        raw = str(entry.get("path", "")).strip()
        if not raw:
            continue
        path = as_path(raw)
        if path.is_dir() and path not in roots:
            roots.append(path)
    return roots


def project_tasks_dir(project_root):
    return Path(project_root) / "pipeline" / "tasks"


def find_task(task_id, project=None):
    """Return (project_root, task_dir) for a task ID.

    If project is given, only that project is checked. Otherwise the local
    project root and every project from pipeline/projects.json are searched.
    """
    if project:
        root = resolve_project(project)
        task_dir = project_tasks_dir(root) / task_id
        return root, (task_dir if task_dir.is_dir() else None)

    for root in known_projects():
        task_dir = project_tasks_dir(root) / task_id
        if task_dir.is_dir():
            return root, task_dir
    return None, None


def all_tasks():
    found = []
    for root in known_projects():
        tasks_dir = project_tasks_dir(root)
        if not tasks_dir.exists():
            continue
        for path in sorted(tasks_dir.iterdir()):
            if path.is_dir() and TASK_RE.fullmatch(path.name):
                found.append((root, path))
    return found


def next_task_id(project_root):
    tasks_dir = project_tasks_dir(project_root)
    numbers = []
    if tasks_dir.exists():
        for path in tasks_dir.iterdir():
            match = re.fullmatch(r"TASK-(\d+)", path.name)
            if match and path.is_dir():
                numbers.append(int(match.group(1)))
    return f"TASK-{max(numbers, default=0) + 1:04d}"


def render(text, values):
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def ensure_task_layout(project_root):
    tasks_dir = project_tasks_dir(project_root)
    for sub in ("", "03-assignments", "04-development", "05-verification"):
        (tasks_dir / sub).mkdir(parents=True, exist_ok=True)
    return tasks_dir


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def table_value(text, key):
    match = re.search(
        r"\|\s*" + re.escape(key) + r"\s*\|\s*([^|\n]*?)\s*\|",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def line_value(text, key):
    match = re.search(
        r"^\s*" + re.escape(key) + r"\s*:\s*(.+?)\s*$",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def update_table_value(text, key, value):
    pattern = re.compile(
        r"(\|\s*" + re.escape(key) + r"\s*\|\s*)([^|\n]*?)(\s*\|)",
        re.IGNORECASE,
    )
    if pattern.search(text):
        return pattern.sub(lambda m: m.group(1) + value + m.group(3), text, count=1)

    pattern = re.compile(
        r"^(\s*" + re.escape(key) + r"\s*:\s*).*$",
        re.MULTILINE | re.IGNORECASE,
    )
    return pattern.sub(lambda m: m.group(1) + value, text, count=1)


def has_verdict(text, expected):
    return line_value(text, "Verdict").upper() == expected.upper()


def normalize_mode(raw):
    return str(raw or "").strip().lower()


def load_status(task_dir):
    try:
        return json.loads((Path(task_dir) / "status.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
