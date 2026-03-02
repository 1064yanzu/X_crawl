#!/usr/bin/env bash
set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
HELPER_PY="$SCRIPT_DIR/diagnose_api_flow.py"

KEYWORD="${DIAG_KEYWORD:-ChatGPT}"
API_PORT="${DIAG_API_PORT:-18080}"
TASK_TIMEOUT="${DIAG_TASK_TIMEOUT:-240}"
POLL_INTERVAL="${DIAG_POLL_INTERVAL:-5}"
MAX_COUNT="${DIAG_MAX_COUNT:-20}"
BASE_URL=""
SKIP_SEARCH=0
REUSE_RUNNING=1

USER_PYTHON_BIN="${DIAG_PYTHON_BIN:-}"
BACKEND_PID=""
STARTED_BACKEND=0

usage() {
  cat <<EOF
X_crawl Linux 一键诊断脚本

用法:
  ./scripts/diagnose-linux.sh [options]

选项:
  --keyword <kw>           搜索关键词 (默认: ChatGPT)
  --api-port <port>        本地诊断 API 端口 (默认: 18080)
  --base-url <url>         直接指定 API 地址，覆盖 --api-port
  --task-timeout <sec>     任务最大等待秒数 (默认: 240)
  --poll-interval <sec>    轮询间隔秒数 (默认: 5)
  --max-count <n>          诊断任务 max_count (默认: 20)
  --python-bin <path>      指定 Python 可执行文件
  --skip-search            仅做环境/网络/服务健康，不创建搜索任务
  --no-reuse-running       不复用已运行后端，强制拉起临时后端
  -h, --help               显示帮助

输出:
  backend/logs/diagnose/<timestamp>/
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keyword)
      KEYWORD="${2:-}"; shift 2 ;;
    --api-port)
      API_PORT="${2:-}"; shift 2 ;;
    --base-url)
      BASE_URL="${2:-}"; shift 2 ;;
    --task-timeout)
      TASK_TIMEOUT="${2:-}"; shift 2 ;;
    --poll-interval)
      POLL_INTERVAL="${2:-}"; shift 2 ;;
    --max-count)
      MAX_COUNT="${2:-}"; shift 2 ;;
    --python-bin)
      USER_PYTHON_BIN="${2:-}"; shift 2 ;;
    --skip-search)
      SKIP_SEARCH=1; shift ;;
    --no-reuse-running)
      REUSE_RUNNING=0; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "[ERROR] 未知参数: $1"
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$BASE_URL" ]]; then
  BASE_URL="http://127.0.0.1:${API_PORT}"
fi

TS="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$BACKEND_DIR/logs/diagnose/$TS"
mkdir -p "$OUT_DIR"
SUMMARY_MD="$OUT_DIR/summary.md"
RAW_LOG="$OUT_DIR/raw.log"
SERVER_LOG="$OUT_DIR/backend-server.log"

if [[ -n "$USER_PYTHON_BIN" ]]; then
  PYTHON_BIN="$USER_PYTHON_BIN"
elif [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "[FATAL] 找不到可用 Python，请安装 python3 或提供 --python-bin" | tee -a "$RAW_LOG"
  exit 2
fi

on_exit() {
  if [[ "$STARTED_BACKEND" -eq 1 ]] && [[ -n "$BACKEND_PID" ]]; then
    if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
      kill "$BACKEND_PID" >/dev/null 2>&1 || true
      sleep 1
      kill -9 "$BACKEND_PID" >/dev/null 2>&1 || true
    fi
  fi
}
trap on_exit EXIT

log() {
  echo "[$(date '+%F %T')] $*" | tee -a "$RAW_LOG"
}

append_md() {
  echo "$*" >> "$SUMMARY_MD"
}

run_cmd() {
  local title="$1"
  shift
  log "[RUN] $title"
  {
    echo "\n### $title"
    echo '```bash'
    printf '%q ' "$@"
    echo
    echo '```'
    echo
    echo '```text'
    "$@"
    local rc=$?
    echo
    echo "[exit_code] $rc"
    echo '```'
    echo
    return $rc
  } >> "$SUMMARY_MD" 2>> "$RAW_LOG"
  return $?
}

api_health_ok() {
  curl -fsS --max-time 5 "$BASE_URL/health" >/dev/null 2>&1
}

start_backend() {
  log "尝试启动临时后端: $BASE_URL"
  (
    cd "$BACKEND_DIR" || exit 1
    export PYTHONPATH="$BACKEND_DIR"
    export API_HOST="127.0.0.1"
    export API_PORT
    if [[ "$(uname -s)" == "Linux" && -z "${DISPLAY:-}" ]]; then
      export BROWSER_HEADLESS="${BROWSER_HEADLESS:-true}"
    fi
    exec "$PYTHON_BIN" -m uvicorn api.main:app --host 127.0.0.1 --port "$API_PORT"
  ) > "$SERVER_LOG" 2>&1 &
  BACKEND_PID=$!
  STARTED_BACKEND=1

  local ok=0
  for _ in {1..60}; do
    if api_health_ok; then
      ok=1
      break
    fi
    sleep 1
  done
  if [[ "$ok" -ne 1 ]]; then
    log "[ERROR] 后端启动失败，未在 60s 内通过 /health"
    return 1
  fi
  log "临时后端启动成功，PID=$BACKEND_PID"
  return 0
}

{
  echo "# X_crawl Linux 一键诊断报告"
  echo
  echo "- 生成时间: $(date '+%F %T')"
  echo "- 仓库路径: $ROOT_DIR"
  echo "- 输出目录: $OUT_DIR"
  echo "- Python: $PYTHON_BIN"
  echo "- API: $BASE_URL"
  echo "- 关键词: $KEYWORD"
  echo "- 任务超时: ${TASK_TIMEOUT}s"
  echo
} > "$SUMMARY_MD"

log "开始执行 Linux 全链路诊断"

run_cmd "系统信息" bash -lc "uname -a; echo; date -Iseconds; echo; [ -f /etc/os-release ] && cat /etc/os-release || true"
run_cmd "资源与显示服务" bash -lc "echo DISPLAY=\"\${DISPLAY:-<empty>}\"; echo WAYLAND_DISPLAY=\"\${WAYLAND_DISPLAY:-<empty>}\"; echo; df -h /dev/shm 2>/dev/null || true; echo; free -h 2>/dev/null || vm_stat 2>/dev/null || true"
run_cmd "Python 与依赖版本" bash -lc "'$PYTHON_BIN' -V; '$PYTHON_BIN' -m pip -V; '$PYTHON_BIN' -m pip show DrissionPage pydantic fastapi uvicorn || true"
run_cmd "浏览器可执行文件" bash -lc "command -v google-chrome || true; google-chrome --version || true; command -v chromium-browser || true; chromium-browser --version || true; command -v chromium || true; chromium --version || true"
run_cmd "DNS 解析检查" bash -lc "getent hosts x.com 2>/dev/null || nslookup x.com 2>/dev/null || true; getent hosts api.x.com 2>/dev/null || nslookup api.x.com 2>/dev/null || true"
run_cmd "HTTPS 连通性检查" bash -lc "curl -I -L --max-time 15 https://x.com 2>&1 | sed -n '1,20p'; echo; curl -I -L --max-time 15 https://api.x.com 2>&1 | sed -n '1,20p'"
run_cmd "TCP 443 端口连通性" "$PYTHON_BIN" - <<'PY'
import socket
for host in ("x.com", "api.x.com"):
    try:
        with socket.create_connection((host, 443), timeout=8):
            print(f"[OK] tcp://{host}:443")
    except Exception as e:
        print(f"[FAIL] tcp://{host}:443 -> {e}")
PY

if [[ "$REUSE_RUNNING" -eq 1 ]] && api_health_ok; then
  log "检测到已有后端可用，复用当前实例: $BASE_URL"
  append_md "## 后端实例"
  append_md "- 复用已有后端: 是"
  append_md
else
  append_md "## 后端实例"
  append_md "- 复用已有后端: 否（启动临时实例）"
  append_md
  if ! start_backend; then
    append_md "- 启动结果: 失败（详见 $SERVER_LOG）"
    echo
    echo "诊断失败：后端无法拉起。查看: $SERVER_LOG"
    exit 1
  fi
  append_md "- 启动结果: 成功（PID=${BACKEND_PID}）"
fi

run_cmd "后端健康接口" bash -lc "curl -fsS '$BASE_URL/health'"
run_cmd "当前爬虫配置" bash -lc "curl -fsS '$BASE_URL/api/v1/crawler-config'"
run_cmd "当前 Cookie 概览" bash -lc "curl -fsS '$BASE_URL/api/v1/cookies'"

if [[ "$SKIP_SEARCH" -eq 0 ]]; then
  log "执行搜索任务链路诊断"
  set +e
  "$PYTHON_BIN" "$HELPER_PY" \
    --base-url "$BASE_URL" \
    --keyword "$KEYWORD" \
    --task-timeout "$TASK_TIMEOUT" \
    --poll-interval "$POLL_INTERVAL" \
    --max-count "$MAX_COUNT" \
    --output-dir "$OUT_DIR" >> "$RAW_LOG" 2>&1
  FLOW_RC=$?

  append_md "## 搜索链路诊断"
  append_md "- 执行结果退出码: ${FLOW_RC}"
  append_md "- 结构化摘要: $OUT_DIR/diagnosis_summary.md"
  append_md "- 原始 JSON: $OUT_DIR/diagnosis_summary.json"
  append_md

  if [[ -f "$OUT_DIR/diagnosis_summary.md" ]]; then
    append_md "### API 诊断摘要"
    cat "$OUT_DIR/diagnosis_summary.md" >> "$SUMMARY_MD"
    append_md
  fi

  if [[ -f "$OUT_DIR/task_id.txt" ]]; then
    TASK_ID="$(tr -d '\r\n' < "$OUT_DIR/task_id.txt")"
    if [[ -n "$TASK_ID" ]]; then
      log "提取 task_id=$TASK_ID 相关日志"
      {
        echo "# task_id: $TASK_ID"
        echo
        if [[ -f "$BACKEND_DIR/logs/xcrawl.log" ]]; then
          echo "## 来源: backend/logs/xcrawl.log"
          rg -n "$TASK_ID|ERROR|WARNING|搜索页面反复出现错误|检测到错误页面|软恢复重试|风险页" "$BACKEND_DIR/logs/xcrawl.log" || true
          echo
        fi
        if [[ -f "$SERVER_LOG" ]]; then
          echo "## 来源: backend-server.log"
          rg -n "$TASK_ID|ERROR|WARNING|搜索页面反复出现错误|检测到错误页面|软恢复重试|风险页" "$SERVER_LOG" || true
        fi
      } > "$OUT_DIR/task_related.log" 2>&1
      append_md "- task 相关日志: $OUT_DIR/task_related.log"
      append_md
    fi
  fi
else
  append_md "## 搜索链路诊断"
  append_md "- 已跳过（--skip-search）"
  append_md
fi

append_md "## 关键产物"
append_md "- 总结报告: $SUMMARY_MD"
append_md "- 原始执行日志: $RAW_LOG"
append_md "- API 诊断 JSON: $OUT_DIR/diagnosis_summary.json"
append_md "- task 相关日志: $OUT_DIR/task_related.log"
append_md

log "诊断完成，输出目录: $OUT_DIR"
echo
echo "诊断完成。请把以下文件发我："
echo "1) $SUMMARY_MD"
echo "2) $OUT_DIR/diagnosis_summary.json"
echo "3) $OUT_DIR/task_related.log"
