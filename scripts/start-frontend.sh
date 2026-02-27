#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
PORT="${FRONTEND_PORT:-3000}"

if ! command -v npm >/dev/null 2>&1; then
  echo "[error] 未找到 npm，请先安装 Node.js 18+"
  exit 1
fi

cd "$FRONTEND_DIR"

if [[ "${1:-}" == "--prod" ]]; then
  npm run build
  exec npm run start -- --port "$PORT"
fi

exec npm run dev -- --port "$PORT"
