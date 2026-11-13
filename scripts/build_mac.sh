#!/usr/bin/env bash
# Сборка LocalTranscriber.app для macOS.
#
#   bash scripts/build_mac.sh
#
# Результат: dist/LocalTranscriber.app и dist/LocalTranscriber-macos.zip.
# Модели в сборку не входят: они скачиваются при первом запуске
# (~/Library/Application Support/LocalTranscriber/models).
#
# Переменные:
#   PYTHON=python3.13   — интерпретатор для .venv (по умолчанию python3)
#   LT_NO_VENV=1        — не создавать .venv, использовать текущий python
#                         (так делает CI, где зависимости уже установлены)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if [ "${LT_NO_VENV:-0}" = "1" ]; then
  PYTHON_BIN="$(command -v python)"
else
  PYTHON="${PYTHON:-python3}"
  if [ ! -x ".venv/bin/python" ]; then
    echo "Создаю виртуальное окружение…"
    "$PYTHON" -m venv .venv
  fi
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt pyinstaller==6.22.3
  PYTHON_BIN=".venv/bin/python"
fi

echo "Собираю приложение (2–5 минут)…"
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --windowed \
  --onedir \
  --name LocalTranscriber \
  --osx-bundle-identifier ru.localtranscriber.app \
  --paths src \
  --collect-all tkinterdnd2 \
  --collect-all rapidocr \
  --collect-all ctranslate2 \
  --collect-all onnxruntime \
  --collect-all av \
  --collect-all faster_whisper \
  --hidden-import pymupdf \
  --hidden-import truststore \
  scripts/launcher.py

APP="dist/LocalTranscriber.app"
if [ ! -d "$APP" ]; then
  echo "Сборка не создала $APP" >&2
  exit 1
fi

# Без Apple Developer ID: ad-hoc подпись. Первый запуск — правый клик → «Открыть».
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" || true

echo "Проверяю, что библиотеки распознавания попали в сборку…"
"$APP/Contents/MacOS/LocalTranscriber" --diagnose "$ROOT/dist/macos-diagnose.json"
cat "$ROOT/dist/macos-diagnose.json"

ditto -c -k --keepParent "$APP" "dist/LocalTranscriber-macos.zip"
echo "Готово: dist/LocalTranscriber.app и dist/LocalTranscriber-macos.zip"
