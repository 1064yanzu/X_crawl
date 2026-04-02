#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

API_BASE = "http://127.0.0.1:8000"
STATE_PATH = Path(__file__).resolve().parents[1] / "run" / "monitor_state.json"
PLATFORMS = {"x", "weibo"}


@dataclass
class MonitorResult:
    message: str
    changed: bool = False


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def api_json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    url = f"{API_BASE}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with request.urlopen(req, timeout=20) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset)
            return json.loads(body) if body else None
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {body}") from e
    except error.URLError as e:
        raise RuntimeError(f"请求失败 {method} {path}: {e}") from e


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "task_counts": {},
        "task_replies": {},
        "comment_backfill_sources": [],
        "last_run_at": None,
    }


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def segment_done(task: dict[str, Any]) -> bool:
    raw = task.get("segment_progress") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    enabled = bool(raw.get("enabled"))
    total = int(raw.get("total_segments") or 0)
    completed = int(raw.get("completed_segments") or 0)
    if enabled and total > 0:
        return completed >= total
    # 非分段任务，done 视为已完成
    return str(task.get("status") or "") == "done"


def summarize_platform(tasks: list[dict[str, Any]], prev_counts: dict[str, int], prev_replies: dict[str, int]) -> tuple[dict[str, dict[str, int]], int, int]:
    by_platform: dict[str, dict[str, int]] = {p: {"tasks": 0, "new_posts": 0, "new_replies": 0} for p in sorted(PLATFORMS)}
    total_posts = 0
    total_replies = 0
    for task in tasks:
        tid = str(task.get("task_id") or "")
        platform = str(task.get("platform") or "").lower()
        if platform not in PLATFORMS:
            continue
        by_platform.setdefault(platform, {"tasks": 0, "new_posts": 0, "new_replies": 0})
        by_platform[platform]["tasks"] += 1
        count = int(task.get("result_count") or 0)
        replies = int(task.get("replies_fetched") or 0)
        total_posts += max(0, count - int(prev_counts.get(tid, 0) or 0))
        total_replies += max(0, replies - int(prev_replies.get(tid, 0) or 0))
        by_platform[platform]["new_posts"] += max(0, count - int(prev_counts.get(tid, 0) or 0))
        by_platform[platform]["new_replies"] += max(0, replies - int(prev_replies.get(tid, 0) or 0))
    return by_platform, total_posts, total_replies


def main() -> int:
    state = load_state()
    tasks = api_json("GET", "/api/v1/tasks?include_payload=false") or []
    tasks = [t for t in tasks if str(t.get("platform") or "").lower() in PLATFORMS]

    prev_counts = state.get("task_counts", {}) or {}
    prev_replies = state.get("task_replies", {}) or {}
    backfilled = set(state.get("comment_backfill_sources", []) or [])

    by_platform, total_new_posts, total_new_replies = summarize_platform(tasks, prev_counts, prev_replies)

    changed = False

    search_tasks = [t for t in tasks if str(t.get("task_kind") or "search") == "search"]
    incomplete_search_tasks = [
        t for t in search_tasks
        if str(t.get("status") or "") not in {"done"} or not segment_done(t)
    ]
    done_search_tasks = [t for t in search_tasks if str(t.get("status") or "") == "done" and segment_done(t)]

    backfill_created: list[str] = []
    if search_tasks and not incomplete_search_tasks:
        eligible_ids = [
            str(t.get("task_id") or "")
            for t in done_search_tasks
            if str(t.get("task_id") or "") and str(t.get("task_id") or "") not in backfilled
        ]
        if eligible_ids:
            payload = {
                "task_ids": eligible_ids,
                "reply_depth": 2,
                "max_replies_per_tweet": 0,
                "queue_name": "自动评论补采",
            }
            try:
                resp = api_json("POST", "/api/v1/comment-backfill/from-tasks", payload)
                for source in (resp or {}).get("sources", []) or []:
                    if source.get("status") == "created" and source.get("source_task_id"):
                        sid = str(source["source_task_id"])
                        backfilled.add(sid)
                        backfill_created.append(f"{source.get('platform')}:{source.get('source_keyword') or sid[:8]}")
                if backfill_created:
                    changed = True
            except Exception as e:
                backfill_created.append(f"补采触发失败: {e}")

    state["task_counts"] = {str(t.get("task_id") or ""): int(t.get("result_count") or 0) for t in tasks}
    state["task_replies"] = {str(t.get("task_id") or ""): int(t.get("replies_fetched") or 0) for t in tasks}
    state["comment_backfill_sources"] = sorted(backfilled)
    state["last_run_at"] = now_utc().isoformat()
    save_state(state)

    parts: list[str] = []
    parts.append(f"巡检完成：X {by_platform.get('x', {}).get('tasks', 0)} 个任务，微博 {by_platform.get('weibo', {}).get('tasks', 0)} 个任务。")
    parts.append(f"本轮新增帖子 {total_new_posts} 条，新增评论 {total_new_replies} 条。")
    if incomplete_search_tasks:
        parts.append(f"搜索分段未全跑完：还有 {len(incomplete_search_tasks)} 个搜索任务未完成。")
    else:
        if search_tasks:
            parts.append("所有搜索任务的时间分段都已跑完。")
        else:
            parts.append("当前没有搜索任务。")
    if backfill_created:
        parts.append("已触发评论补采：" + "；".join(backfill_created[:8]) + ("；…" if len(backfill_created) > 8 else ""))

    print(" ".join(parts))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"巡检失败：{exc}")
        raise
