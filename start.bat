@echo off
title AI Video Analysis System
cd /d "%~dp0"
echo ========================================
echo   AI Video Analysis System
echo   One-Click Startup
echo ========================================
echo.
echo Starting containers and services...
echo.
powershell -ExecutionPolicy Bypass -File "scripts\start.ps1"
pause
