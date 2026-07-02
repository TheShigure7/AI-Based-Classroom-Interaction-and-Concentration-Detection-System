@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File ".\scripts\start_backend.ps1"
pause
