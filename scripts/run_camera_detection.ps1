$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$installScript = Join-Path $projectRoot "scripts\install_backend_deps.ps1"
$previewScript = Join-Path $projectRoot "scripts\preview_camera.ps1"

if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual environment not found. Installing dependencies first..."
    & $installScript
}

& $previewScript
