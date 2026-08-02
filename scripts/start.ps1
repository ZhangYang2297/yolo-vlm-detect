function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
}

function Test-ContainerRunning {
    param([string]$Name)
    $container = docker ps --filter "name=^/${Name}$" --format "{{.Names}}" 2>$null
    return [bool]$container
}

function Start-Container {
    param(
        [string]$Name,
        [string]$Image,
        [string[]]$Ports,
        [string[]]$Env,
        [string]$Volume,
        [string]$Cmd,
        [string]$ConfigMount
    )

    Write-Log "Starting container: ${Name} (${Image})"

    $args = @("run", "-d", "--name", $Name, "--restart", "unless-stopped")

    foreach ($p in $Ports) { $args += "-p"; $args += $p }
    foreach ($e in $Env) { $args += "-e"; $args += $e }
    if ($Volume) { $args += "-v"; $args += $Volume }
    if ($ConfigMount) { $args += "-v"; $args += $ConfigMount }

    $args += $Image
    if ($Cmd) { $args += $Cmd.Split(" ", [StringSplitOptions]::RemoveEmptyEntries) }

    $result = & docker $args 2>&1
    if ($LASTEXITCODE -ne 0) {
        & docker start $Name 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Failed to start container ${Name}: ${result}" "ERROR"
            return $false
        }
    }
    return $true
}

function Wait-ContainerHealthy {
    param([string]$Name, [int]$TimeoutSeconds = 30)
    $start = Get-Date
    while ((Get-Date) - $start -lt [TimeSpan]::FromSeconds($TimeoutSeconds)) {
        $status = docker inspect $Name --format "{{.State.Status}}" 2>$null
        if ($status -eq "running") {
            Write-Log "Container ${Name} is running"
            return $true
        }
        Start-Sleep -Seconds 2
    }
    Write-Log "Container ${Name} did not become healthy within ${TimeoutSeconds}s" "WARN"
    return $false
}

# ============================================================
Clear-Host
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  AI Video Analysis System - Startup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check Docker
Write-Log "Checking Docker..."
$dockerOk = docker info 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Log "Docker is not running. Please start Docker Desktop first." "ERROR"
    exit 1
}
Write-Log "Docker is running"

# Step 1: Start containers
Write-Host ""
Write-Host ">>> Step 1/3: Starting Infrastructure Containers ..." -ForegroundColor Yellow

# Redis
if (-not (Test-ContainerRunning "vlm-redis")) {
    & docker rm -f vlm-redis 2>$null
    Start-Container -Name "vlm-redis" -Image "redis:7-alpine" -Ports @("6379:6379") -Volume "vlm_redis_data:/data"
}
Wait-ContainerHealthy "vlm-redis" -TimeoutSeconds 15

# MySQL
if (-not (Test-ContainerRunning "vlm-mysql")) {
    & docker rm -f vlm-mysql 2>$null
    Start-Container -Name "vlm-mysql" -Image "mysql:8.4" -Ports @("3307:3306") -Env @("MYSQL_ROOT_PASSWORD=root123456", "MYSQL_DATABASE=video_analyzer") -Volume "vlm_mysql_data:/var/lib/mysql"
}
Wait-ContainerHealthy "vlm-mysql" -TimeoutSeconds 30

# MinIO
if (-not (Test-ContainerRunning "vlm-minio")) {
    & docker rm -f vlm-minio 2>$null
    Start-Container -Name "vlm-minio" -Image "minio/minio:latest" -Ports @("9000:9000", "9001:9001") -Env @("MINIO_ROOT_USER=minioadmin", "MINIO_ROOT_PASSWORD=minioadmin123") -Volume "vlm_minio_data:/data" -Cmd "server /data --console-address :9001"
}
Wait-ContainerHealthy "vlm-minio" -TimeoutSeconds 15

# MediaMTX
if (-not (Test-ContainerRunning "vlm-mediamtx")) {
    & docker rm -f vlm-mediamtx 2>$null
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
    Start-Container -Name "vlm-mediamtx" -Image "bluenviron/mediamtx:latest" -Ports @("8554:8554", "8888:8888", "8889:8889", "8189:8189/udp") -ConfigMount "${ProjectRoot}/mediamtx.yml:/mediamtx.yml"
}
Wait-ContainerHealthy "vlm-mediamtx" -TimeoutSeconds 15

Write-Host ""
Write-Host "All containers are running!" -ForegroundColor Green
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-Object -Skip 1 | ForEach-Object { Write-Host "  $_" }

# Step 2: Check Python
Write-Host ""
Write-Host ">>> Step 2/3: Checking Python Environment ..." -ForegroundColor Yellow
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Log "Python not found" "ERROR"
    exit 1
}
Write-Log "Python: $($python.Source)"

# Quick dep check
$ProjectRoot = Split-Path -Parent $PSScriptRoot
try {
    python -c "from flask import Flask; print('Flask OK')" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Installing Python dependencies..."
        pip install -r "${ProjectRoot}/requirements.txt" -q
    }
}
catch {
    Write-Log "Dependency check failed: $_" "WARN"
}

# Step 3: Start Flask
Write-Host ""
Write-Host ">>> Step 3/3: Starting Backend Service ..." -ForegroundColor Yellow
Set-Location $ProjectRoot
$env:PYTHONPATH = $ProjectRoot

Write-Log "Starting Flask on http://127.0.0.1:8080"
Write-Log "Monitor page: http://127.0.0.1:8080/monitor"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  System Ready!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Monitor:  http://127.0.0.1:8080/monitor" -ForegroundColor White
Write-Host "  Dashboard: http://127.0.0.1:8080/" -ForegroundColor White
Write-Host "  MinIO:    http://127.0.0.1:9001" -ForegroundColor White
Write-Host "  HLS:      http://127.0.0.1:8888/pedestrian/index.m3u8" -ForegroundColor White
Write-Host ""
Write-Host "  Press Ctrl+C to stop the server" -ForegroundColor DarkGray
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Start-Process "http://127.0.0.1:8080/monitor"
python app.py
