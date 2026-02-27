$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$python = Join-Path $backend ".venv/Scripts/python.exe"

if (-not (Test-Path $python)) {
  Write-Error "未找到后端虚拟环境: $python`n请先在 backend 目录执行: py -m venv .venv ; .venv\\Scripts\\Activate.ps1 ; pip install -r requirements.txt"
}

if (-not $env:API_HOST) { $env:API_HOST = "0.0.0.0" }
if (-not $env:API_PORT) { $env:API_PORT = "8000" }
if (-not $env:PYTHONPATH) { $env:PYTHONPATH = $backend }

Push-Location $backend
try {
  if ($args.Count -gt 0 -and $args[0] -eq "--prod") {
    $workers = if ($env:UVICORN_WORKERS) { $env:UVICORN_WORKERS } else { "1" }
    & $python -m uvicorn api.main:app --host $env:API_HOST --port $env:API_PORT --workers $workers
  }
  else {
    & $python -m uvicorn api.main:app --reload --host $env:API_HOST --port $env:API_PORT
  }
}
finally {
  Pop-Location
}
