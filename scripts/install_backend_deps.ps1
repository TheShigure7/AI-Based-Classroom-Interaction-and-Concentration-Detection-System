$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirements = Join-Path $projectRoot "backend\requirements.txt"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating project virtual environment..."
    python -m venv $venvDir
}

Write-Host "Upgrading pip..."
& $venvPython -m pip install --upgrade pip

Write-Host "Installing backend dependencies..."
& $venvPython -m pip install -r $requirements

Write-Host "Backend dependencies installed."
