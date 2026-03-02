#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[error] 未找到后端虚拟环境: $PYTHON_BIN"
  echo "请先在 backend 目录执行: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

export PYTHONPATH="$BACKEND_DIR"
export API_HOST="${API_HOST:-0.0.0.0}"
export API_PORT="${API_PORT:-8000}"

if [[ "$(uname -s)" == "Linux" && -z "${DISPLAY:-}" ]]; then
  if command -v Xvfb >/dev/null 2>&1; then
    export DISPLAY="${DISPLAY:-:99}"
    if ! pgrep -af "Xvfb ${DISPLAY}" >/dev/null 2>&1; then
      nohup Xvfb "${DISPLAY}" -screen 0 1920x1080x24 >/tmp/xcrawl-xvfb.log 2>&1 &
      sleep 1
    fi
    # 有虚拟显示时默认使用有头模式，降低 X 反爬误伤概率
    export BROWSER_HEADLESS="${BROWSER_HEADLESS:-false}"
  else
    export BROWSER_HEADLESS="${BROWSER_HEADLESS:-true}"
  fi
fi

cd "$BACKEND_DIR"

if [[ "${1:-}" == "--prod" ]]; then
  WORKERS="${UVICORN_WORKERS:-1}"
  exec "$PYTHON_BIN" -m uvicorn api.main:app --host "$API_HOST" --port "$API_PORT" --workers "$WORKERS"
fi

exec "$PYTHON_BIN" -m uvicorn api.main:app --reload --host "$API_HOST" --port "$API_PORT"
