# 宿主机跑 API（热重载）
$ErrorActionPreference = "Stop"
Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "backend")

if (-not (Test-Path .venv\Scripts\python.exe)) {
  Write-Host "Creating venv..."
  python -m venv .venv
  .\.venv\Scripts\pip install -r requirements.txt
}

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host "Created .env from .env.example"
}

Write-Host "Running migrations..."
.\.venv\Scripts\alembic.exe upgrade head

Write-Host "API http://127.0.0.1:8001/docs  (need ffmpeg in PATH for extract)"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
