#!/usr/bin/env python3
"""X_crawl API diagnosis helper.

负责跑真实任务链路并产出结构化 JSON/Markdown 报告，供 diagnose-linux.sh 调用。
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TERMINAL_STATUSES = {"done", "failed", "stopped"}


@dataclass
class HttpResult:
    ok: bool
    status_code: int
    data: Any
    error: str


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def http_json(base_url: str, method: str, path: str, payload: dict | None = None, timeout: float = 20.0) -> HttpResult:
    url = f"{base_url.rstrip('/')}{path}"
    body_bytes = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url=url, method=method.upper(), data=body_bytes, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed: Any
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw}
            return HttpResult(ok=True, status_code=int(resp.getcode() or 0), data=parsed, error="")
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return HttpResult(ok=False, status_code=int(e.code or 0), data=parsed, error=f"HTTPError: {e}")
    except URLError as e:
        return HttpResult(ok=False, status_code=0, data={}, error=f"URLError: {e}")
    except Exception as e:  # pragma: no cover
        return HttpResult(ok=False, status_code=0, data={}, error=f"Exception: {e}")


def classify(final_task: dict | None, timed_out: bool) -> tuple[str, str]:
    if timed_out:
        return "timeout_running", "任务在限定时间内未进入终态"

    if not final_task:
        return "no_task_data", "未获取到任务终态数据"

    status = (final_task.get("status") or "").lower()
    error = str(final_task.get("error") or "")
    phase = str(final_task.get("phase") or "")
    risk_state = str(final_task.get("risk_state") or "")
    result_count = int(final_task.get("result_count") or 0)

    if status == "done":
        if result_count > 0:
            return "success", f"任务完成，获取到 {result_count} 条推文"
        return "done_but_empty", "任务完成但结果为空，可能是关键词本身结果为空或过滤过严"

    if status == "failed":
        merged = f"{error} | {phase} | {risk_state}".lower()
        if "搜索页面反复出现错误" in error:
            return "search_page_error", "搜索页反复错误，通常是风控/网络质量/浏览器指纹问题"
        if "未检测到 x 登录状态" in error.lower() or "登录" in merged:
            return "login_invalid", "登录态不可用，需重新注入有效 Cookie 或复用已登录浏览器"
        if ("challenge" in merged) or ("rate_limited" in merged) or ("风控" in merged):
            return "risk_or_rate_limit", "命中风控挑战或限流"
        if "timeout" in merged or "超时" in merged:
            return "packet_timeout", "页面可访问但监听目标数据包超时"
        return "failed_other", "任务失败，但错误类型不在预设分类内"

    if status == "stopped":
        return "stopped", "任务被主动终止"

    return "non_terminal", f"任务状态仍为 {status or 'unknown'}"


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# X_crawl 诊断报告（API 链路）")
    lines.append("")
    lines.append(f"- 生成时间: `{summary.get('generated_at', '')}`")
    lines.append(f"- 目标 API: `{summary.get('base_url', '')}`")
    lines.append(f"- 诊断关键词: `{summary.get('keyword', '')}`")
    lines.append(f"- 任务 ID: `{summary.get('task_id', 'N/A')}`")
    lines.append(f"- 结论分类: `{summary.get('classification', {}).get('type', 'unknown')}`")
    lines.append(f"- 结论说明: {summary.get('classification', {}).get('reason', '')}")
    lines.append("")

    health = summary.get("health", {})
    lines.append("## 1. 服务健康")
    lines.append(f"- 请求成功: `{health.get('ok', False)}`")
    lines.append(f"- HTTP 状态码: `{health.get('status_code', 0)}`")
    lines.append(f"- 平台: `{health.get('data', {}).get('platform', 'unknown')}`")
    lines.append(f"- 浏览器路径: `{health.get('data', {}).get('browser_path', '')}`")
    lines.append("")

    cookies = summary.get("cookies", {})
    lines.append("## 2. Cookie 状态")
    if cookies.get("ok"):
        lines.append(f"- 持久化 Cookie 数量: `{cookies.get('data', {}).get('count', 0)}`")
    else:
        lines.append(f"- 获取失败: `{cookies.get('error', '')}`")
    lines.append("")

    lines.append("## 3. 任务轨迹")
    history = summary.get("history", [])
    if not history:
        lines.append("- 无任务轨迹数据")
    else:
        for item in history:
            lines.append(
                "- "
                f"{item.get('ts', '')} | status={item.get('status', '')} | "
                f"page={item.get('current_page', '')} | count={item.get('result_count', '')} | "
                f"phase={item.get('phase', '')}"
            )
    lines.append("")

    final_task = summary.get("final_task") or {}
    lines.append("## 4. 终态详情")
    lines.append(f"- status: `{final_task.get('status', 'unknown')}`")
    lines.append(f"- phase: `{final_task.get('phase', '')}`")
    lines.append(f"- error: `{final_task.get('error', '')}`")
    lines.append(f"- risk_state: `{final_task.get('risk_state', '')}`")
    lines.append(f"- result_count: `{final_task.get('result_count', 0)}`")
    lines.append(f"- debug_screenshot: `{final_task.get('debug_screenshot', '')}`")
    lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run X_crawl API flow diagnosis")
    parser.add_argument("--base-url", required=True, help="API base URL, e.g. http://127.0.0.1:18080")
    parser.add_argument("--keyword", default="ChatGPT", help="search keyword")
    parser.add_argument("--task-timeout", type=int, default=240, help="task max wait seconds")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="poll interval seconds")
    parser.add_argument("--output-dir", required=True, help="directory to write reports")
    parser.add_argument("--max-count", type=int, default=20, help="max_count for the test task")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "generated_at": _ts(),
        "base_url": args.base_url,
        "keyword": args.keyword,
        "task_timeout": args.task_timeout,
        "poll_interval": args.poll_interval,
    }

    health = http_json(args.base_url, "GET", "/health", timeout=10)
    summary["health"] = {
        "ok": health.ok,
        "status_code": health.status_code,
        "data": health.data,
        "error": health.error,
    }

    config = http_json(args.base_url, "GET", "/api/v1/crawler-config", timeout=10)
    summary["crawler_config"] = {
        "ok": config.ok,
        "status_code": config.status_code,
        "data": config.data,
        "error": config.error,
    }

    cookies = http_json(args.base_url, "GET", "/api/v1/cookies", timeout=10)
    summary["cookies"] = {
        "ok": cookies.ok,
        "status_code": cookies.status_code,
        "data": cookies.data,
        "error": cookies.error,
    }

    if not health.ok:
        summary["classification"] = {
            "type": "backend_unavailable",
            "reason": f"/health 不可用: {health.error}",
        }
        write_json(out_dir / "diagnosis_summary.json", summary)
        (out_dir / "diagnosis_summary.md").write_text(build_markdown(summary), encoding="utf-8")
        return 2

    create_payload = {
        "keyword": args.keyword,
        "max_count": args.max_count,
        "product": "Top",
        "resume": False,
        "fetch_replies": False,
        "max_replies_per_tweet": 20,
        "reply_depth": 1,
        "crawl_strategy": "dfs",
    }

    created = http_json(args.base_url, "POST", "/api/v1/search", payload=create_payload, timeout=20)
    summary["task_create"] = {
        "ok": created.ok,
        "status_code": created.status_code,
        "data": created.data,
        "error": created.error,
    }

    if not created.ok:
        summary["classification"] = {
            "type": "task_create_failed",
            "reason": f"创建任务失败: {created.error}",
        }
        write_json(out_dir / "diagnosis_summary.json", summary)
        (out_dir / "diagnosis_summary.md").write_text(build_markdown(summary), encoding="utf-8")
        return 2

    task_id = str((created.data or {}).get("task_id") or "").strip()
    summary["task_id"] = task_id
    (out_dir / "task_id.txt").write_text(task_id + "\n", encoding="utf-8")

    if not task_id:
        summary["classification"] = {
            "type": "task_id_missing",
            "reason": "创建任务响应缺少 task_id",
        }
        write_json(out_dir / "diagnosis_summary.json", summary)
        (out_dir / "diagnosis_summary.md").write_text(build_markdown(summary), encoding="utf-8")
        return 2

    history: list[dict[str, Any]] = []
    final_task: dict[str, Any] | None = None
    timed_out = False
    deadline = time.time() + max(15, int(args.task_timeout))

    while time.time() < deadline:
        snap = http_json(args.base_url, "GET", f"/api/v1/search/{task_id}?include_tweets=false", timeout=20)
        if not snap.ok:
            history.append(
                {
                    "ts": _ts(),
                    "status": "request_error",
                    "phase": snap.error,
                    "result_count": 0,
                    "current_page": 0,
                }
            )
            time.sleep(max(1.0, args.poll_interval))
            continue

        task = snap.data or {}
        status = str(task.get("status") or "")
        history.append(
            {
                "ts": _ts(),
                "status": status,
                "phase": str(task.get("phase") or ""),
                "error": str(task.get("error") or ""),
                "result_count": int(task.get("result_count") or 0),
                "current_page": int(task.get("current_page") or 0),
            }
        )

        if status in TERMINAL_STATUSES:
            final_task = task
            break

        time.sleep(max(1.0, args.poll_interval))

    if final_task is None:
        timed_out = True
        # 尝试主动终止，避免后台一直跑
        _ = http_json(args.base_url, "POST", f"/api/v1/tasks/{task_id}/stop", payload={}, timeout=10)
        snap = http_json(args.base_url, "GET", f"/api/v1/search/{task_id}?include_tweets=false", timeout=20)
        final_task = snap.data if snap.ok else {}

    summary["history"] = history
    summary["final_task"] = final_task or {}
    cls_type, cls_reason = classify(final_task or {}, timed_out=timed_out)
    summary["classification"] = {"type": cls_type, "reason": cls_reason}

    write_json(out_dir / "diagnosis_summary.json", summary)
    (out_dir / "diagnosis_summary.md").write_text(build_markdown(summary), encoding="utf-8")

    # 仅当明确成功时返回 0，其余返回 1（便于 CI/脚本检测异常）
    return 0 if cls_type == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())