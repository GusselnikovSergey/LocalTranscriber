#!/usr/bin/env bash
# Запуск LocalTranscriber из исходников (macOS/Linux).
# Первый запуск создаёт .venv и ставит зависимости (долго), дальше — секунды.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
if [ ! -x ".venv/bin/python" ]; then
  echo "Создаю виртуальное окружение…"
  "$PYTHON" -m venv .venv
fi

MARKER=".venv/.deps-installed"
if [ ! -f "$MARKER" ]; then
  echo "Устанавливаю зависимости (первый раз, ~1–1.5 ГБ)…"
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  touch "$MARKER"
fi

export PYTHONPATH="$PWD/src"
exec .venv/bin/python -m localtranscriber "$@"
