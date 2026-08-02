@echo off
title AI Video Analysis System - Stop
echo ========================================
echo   Shutting Down...
echo ========================================
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
pause
