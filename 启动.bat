@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "FRONTEND_DIST=%~dp0frontend\dist\index.html"
set "BACKEND_URL=http://127.0.0.1:8000"
set "HEALTH_URL=http://127.0.0.1:8000/api/v1/health"

echo [1/5] Checking virtual environment...
if not exist "%PYTHON_EXE%" (
  echo .venv not found. Please run backend dependency installation first.
  pause
  exit /b 1
)

echo [2/5] Checking frontend build...
if not exist "%FRONTEND_DIST%" (
  echo frontend\dist not found. Trying to build frontend...
  where npm >nul 2>nul
  if errorlevel 1 (
    echo Node.js/npm was not found. Please install Node.js first.
    echo Or run npm run build manually inside the frontend folder.
    pause
    exit /b 1
  )
  pushd "%~dp0frontend"
  call npm run build
  if errorlevel 1 (
    popd
    echo Frontend build failed.
    pause
    exit /b 1
  )
  popd
)

echo [3/5] Checking backend status...
call :health_check
if "!HEALTH_OK!"=="1" (
  echo Backend is already running.
) else (
  echo Backend is not running. Starting demo service...
  start "Classroom Backend" /min cmd /c ""%~dp0scripts\start_demo_backend.bat""
)

echo [4/5] Waiting for backend...
set "STARTED_OK=0"
for /l %%i in (1,1,30) do (
  call :health_check
  if "!HEALTH_OK!"=="1" (
    set "STARTED_OK=1"
    goto :open_browser
  )
  timeout /t 1 /nobreak >nul
)

if not "!STARTED_OK!"=="1" (
  echo Backend startup timed out. Please check dependencies, models, or port usage.
  pause
  exit /b 1
)

:open_browser
echo [5/5] Opening browser...
start "" "%BACKEND_URL%"
echo Demo mode started.
exit /b 0

:health_check
set "HEALTH_OK=0"
for /f "delims=" %%a in ('curl -s "%HEALTH_URL%" 2^>nul') do (
  echo %%a | findstr /C:"\"status\":\"ok\"" >nul
  if not errorlevel 1 set "HEALTH_OK=1"
)
exit /b 0
