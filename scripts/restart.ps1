<#
.SYNOPSIS
    AI Video Analysis System - Restart
.DESCRIPTION
    Stops all services and starts them again.
#>
& "$PSScriptRoot/stop.ps1"
Write-Host ""
Write-Host "Restarting..." -ForegroundColor Yellow
Start-Sleep 2
& "$PSScriptRoot/start.ps1"
