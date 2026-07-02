@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File ".\scripts\install_backend_deps.ps1"
pause
