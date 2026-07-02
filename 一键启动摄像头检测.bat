@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File ".\scripts\preview_camera.ps1"
pause
