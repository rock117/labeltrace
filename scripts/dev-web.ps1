# 宿主机跑前端 Vite（热重载，/api → 8001）
$ErrorActionPreference = "Stop"
Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "frontend")

if (-not (Test-Path node_modules)) {
  Write-Host "npm install..."
  npm install --registry=https://registry.npmmirror.com
}

Write-Host "Web http://127.0.0.1:5173"
npm run dev
