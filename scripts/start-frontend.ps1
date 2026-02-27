$ErrorActionPreference = "Stop"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Error "未找到 npm，请先安装 Node.js 18+"
}

$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root "frontend"
$port = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "3721" }

Push-Location $frontend
try {
  if ($args.Count -gt 0 -and $args[0] -eq "--prod") {
    npm run build
    npm run start -- --port $port
  }
  else {
    npm run dev -- --port $port
  }
}
finally {
  Pop-Location
}
