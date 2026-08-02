<#
.SYNOPSIS
    AI Video Analysis System - Shutdown
#>
$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Shutting Down AI Video Analysis System" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Stop Flask
Write-Host ">>> Stopping Backend ..." -ForegroundColor Yellow
$flaskProc = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "app.py" }
if ($flaskProc) {
    $flaskProc | Stop-Process -Force
    Write-Host "  Flask stopped" -ForegroundColor Green
}

# Stop Docker containers
Write-Host ">>> Stopping Containers ..." -ForegroundColor Yellow
$containers = @("vlm-redis", "vlm-mysql", "vlm-minio", "vlm-mediamtx")
foreach ($name in $containers) {
    $running = docker ps --filter "name=^/${name}$" --format "{{.Names}}" 2>$null
    if ($running) {
        docker stop $name 2>$null | Out-Null
        Write-Host "  ${name} stopped" -ForegroundColor Green
    } else {
        Write-Host "  ${name} not running" -ForegroundColor DarkGray
    }
}

# Kill FFmpeg
$ffmpeg = Get-Process -Name ffmpeg -ErrorAction SilentlyContinue
if ($ffmpeg) {
    $ffmpeg | Stop-Process -Force
    Write-Host "  FFmpeg processes stopped" -ForegroundColor Green
}

Write-Host ""
Write-Host "System shutdown complete." -ForegroundColor Green
