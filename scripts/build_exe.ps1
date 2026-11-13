# Сборка standalone-приложения LocalTranscriber (Windows x64).
#
# Использование:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
#
# Результат: dist\LocalTranscriber\LocalTranscriber.exe (папку можно переносить целиком).
# Модели не входят в сборку: они скачиваются при первом запуске в
# %LOCALAPPDATA%\LocalTranscriber\models.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Не найден .venv. Сначала запустите .\run.ps1 (он создаст окружение)."
    exit 1
}

Write-Host "Проверка зависимостей сборки…"
& $python -m pip install --quiet pyinstaller

Write-Host "Сборка (это занимает 2–4 минуты)…"
# Без --clean: полная очистка кэша анализа на этой машине иногда обрывает сборку;
# повторный запуск переиспользует кэш и собирается стабильно.
& $python -m PyInstaller `
    --noconfirm --onedir --windowed `
    --name LocalTranscriber `
    --paths src `
    --collect-all tkinterdnd2 `
    --collect-all rapidocr `
    --collect-all ctranslate2 `
    --collect-all onnxruntime `
    --collect-all av `
    --collect-all faster_whisper `
    --hidden-import pymupdf `
    --hidden-import truststore `
    --hidden-import faster_whisper `
    scripts\launcher.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Сборка не удалась (код $LASTEXITCODE)."
    exit $LASTEXITCODE
}

$exe = Join-Path $root "dist\LocalTranscriber\LocalTranscriber.exe"
Write-Host "Готово: $exe"

Write-Host "Проверка сборки (движки внутри exe)…"
$report = Join-Path $env:TEMP "localtranscriber-selftest.json"
& $exe --selftest $report `
    "testdata\generated\sample.png" `
    "testdata\generated\digital.pdf" `
    "testdata\generated\speech_en.wav"
$code = $LASTEXITCODE
if (Test-Path $report) {
    Get-Content $report -Encoding UTF8
} else {
    Write-Host "Отчёт самопроверки не создан."
}
if ($code -ne 0) {
    Write-Host "Самопроверка сборки не прошла (код $code)."
    exit $code
}
Write-Host "Сборка и самопроверка прошли."
