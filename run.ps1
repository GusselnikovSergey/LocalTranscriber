# Запуск LocalTranscriber: создаёт окружение при первом старте и открывает окно.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Создаю виртуальное окружение..." -ForegroundColor Cyan
    python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать .venv" }
}

$marker = Join-Path $venv ".deps-installed"
if (-not (Test-Path $marker)) {
    Write-Host "Устанавливаю зависимости (первый запуск, ~1-1.5 ГБ)..." -ForegroundColor Cyan
    & $python -m pip install --upgrade pip | Out-Host
    & $python -m pip install -r (Join-Path $root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Не удалось установить зависимости" }
    New-Item -ItemType File -Path $marker | Out-Null
}

$env:PYTHONPATH = Join-Path $root "src"
& $python -m localtranscriber
