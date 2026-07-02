$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

Set-Location $backendDir
if (-not (Test-Path $venvPython)) {
    throw "未找到项目虚拟环境 Python：$venvPython"
}

$env:CLASSROOM_VIDEO_SOURCE = "http://10.62.111.134:8080"
& $venvPython -m app.preview_camera
