#!/usr/bin/env pwsh
# LumiCreate-Local 开发启动脚本

Write-Host "╔══════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   LumiCreate-Local Dev Mode  ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════╝" -ForegroundColor Cyan

$root = $PSScriptRoot

# 1. Start FastAPI backend
Write-Host "`n[1/3] 启动 Python 后端 (port 18520)..." -ForegroundColor Yellow
$backend = Start-Process python -ArgumentList "$root\backend\main.py" -WorkingDirectory "$root\backend" -PassThru

# 2. Wait for backend
Write-Host "[2/3] 等待后端就绪..." -ForegroundColor Yellow
$maxTry = 15
for ($i = 0; $i -lt $maxTry; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-RestMethod http://127.0.0.1:18520/api/health -TimeoutSec 1 -ErrorAction Stop
        if ($r.status -eq "ok") { Write-Host "      ✓ 后端就绪" -ForegroundColor Green; break }
    } catch {}
    if ($i -eq $maxTry - 1) { Write-Host "      ✗ 后端启动超时" -ForegroundColor Red }
}

# 3. Launch Electron + Vue dev
Write-Host "[3/3] 启动 Electron + Vue..." -ForegroundColor Yellow
$env:NODE_ENV = "development"
Set-Location $root
npx concurrently --kill-others `
    "cd renderer && npx vite --port 5173" `
    "npx wait-on http://localhost:5173 && npx electron ."

# Cleanup backend on exit
if ($backend -and !$backend.HasExited) {
    Write-Host "`n关闭后端进程..." -ForegroundColor Yellow
    Stop-Process -Id $backend.Id -Force
}
