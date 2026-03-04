#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
PORT="${FRONTEND_PORT:-3721}"

if ! command -v npm >/dev/null 2>&1; then
  echo "[error] 未找到 npm，请先安装 Node.js 18+"
  exit 1
fi

cd "$FRONTEND_DIR"

# 限制 Node.js 最大堆内存，防止 OOM
export NODE_OPTIONS="--max-old-space-size=384"

# 显式 --prod 或系统可用内存 <1GB 时自动使用 production 模式
USE_PROD=false
if [[ "${1:-}" == "--prod" ]]; then
  USE_PROD=true
else
  AVAIL_MB=$(awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo "9999")
  if [[ "$AVAIL_MB" -lt 1024 ]]; then
    echo "[info] 可用内存仅 ${AVAIL_MB}MB (<1GB)，自动切换至 production 模式以节省内存"
    USE_PROD=true
  fi
fi

if $USE_PROD; then
  if [[ ! -d ".next" ]] || [[ ! -f ".next/BUILD_ID" ]]; then
    echo "[info] 未检测到构建产物，开始 npm run build ..."
    npm run build
  fi
  echo "[info] 以 production 模式启动，端口 $PORT"
  exec npx next start -p "$PORT"
fi

exec npm run dev -- --port "$PORT"
