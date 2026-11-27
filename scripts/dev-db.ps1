# 只起 Postgres（api/web 在宿主机跑）
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "Stopping api/web containers (if any)..."
docker compose stop api web 2>$null

Write-Host "Starting postgres..."
docker compose up -d postgres

Write-Host ""
Write-Host "Postgres ready: 127.0.0.1:5432  (postgres/postgres/labeltrace)"
Write-Host "Then in two terminals:"
Write-Host "  powershell -File scripts/dev-api.ps1"
Write-Host "  powershell -File scripts/dev-web.ps1"
Write-Host "UI: http://127.0.0.1:5173"
