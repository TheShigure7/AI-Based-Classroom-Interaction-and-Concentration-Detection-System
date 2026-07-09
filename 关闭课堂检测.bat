@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "HEALTH_URL=http://127.0.0.1:8000/api/v1/health"
set "EXIT_URL=http://127.0.0.1:8000/api/v1/app/exit"

echo [1/2] 尝试正常关闭后端...
curl -s -X POST "%EXIT_URL%" >nul 2>nul
timeout /t 1 /nobreak >nul

echo [2/2] 检查 8000 端口是否还有残留进程...
set "PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  set "PID=%%a"
  goto :kill_backend
)

echo 未发现占用 8000 端口的后端进程。
goto :done

:kill_backend
if defined PID (
  taskkill /PID !PID! /F >nul 2>nul
  if errorlevel 1 (
    echo 进程关闭失败，请检查权限或手动结束 PID !PID!。
  ) else (
    echo 后端进程已关闭，PID: !PID!
  )
)

:done
echo 完成。
pause
