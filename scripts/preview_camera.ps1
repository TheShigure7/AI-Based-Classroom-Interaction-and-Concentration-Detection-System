$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

Set-Location $backendDir
if (-not (Test-Path $venvPython)) {
    throw "未找到项目虚拟环境 Python：$venvPython"
}

& $venvPython -m app.preview_camera
