#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

API_BASE = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = PROJECT_ROOT / "run" / "monitor_state.json"
PLATFORMS = {"x", "weibo"}
DB_CANDIDATES = [
    PROJECT_ROOT / "backend" / "tasks.db",
    PROJECT_ROOT / "tasks.db",
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def api_json(method: str, path: str, payload: dict[str, Any] | None = None, retries: int = 2) -> Any:
    url = f"{API_BASE}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = request.Request(url, data=data, method=method.upper(), headers=headers)
        try:
            with request.urlopen(req, timeout=20) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                body = resp.read().decode(charset)
                return json.loads(body) if body else None
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"HTTP {e.code} {method} {path}: {body}")
        except error.URLError as e:
            last_err = RuntimeError(f"请求失败 {method} {path}: {e}")
        if attempt < retries:
            time.sleep(1.2 * (attempt + 1))
    raise last_err or RuntimeError(f"请求失败 {method} {path}")


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
        "comment_backfill_task_state": {},
        "last_run_at": None,
    }


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _select_db_path() -> Path:
    for path in DB_CANDIDATES:
        if path.exists():
            return path
    raise RuntimeError("未找到 tasks.db")


def _load_tasks_from_db() -> list[dict[str, Any]]:
    db_path = _select_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            select
                task_id,
                status,
                platform,
                keyword,
                result_count,
                replies_fetched,
                task_kind,
                risk_state,
                error,
                last_event_at,
                segment_progress_json,
                comment_backfill_progress_json
            from tasks
            order by datetime(created_at) desc
            """
        ).fetchall()
    finally:
        conn.close()

    tasks: list[dict[str, Any]] = []
    for row in rows:
        segment_progress = row["segment_progress_json"]
        comment_backfill_progress = row["comment_backfill_progress_json"]
        try:
            segment_progress = json.loads(segment_progress or "{}")
        except Exception:
            segment_progress = {}
        try:
            comment_backfill_progress = json.loads(comment_backfill_progress or "{}")
        except Exception:
            comment_backfill_progress = {}
        tasks.append(
            {
                "task_id": row["task_id"],
                "status": row["status"],
                "platform": row["platform"],
                "keyword": row["keyword"],
                "result_count": row["result_count"],
                "replies_fetched": row["replies_fetched"],
                "task_kind": row["task_kind"],
                "risk_state": row["risk_state"],
                "error": row["error"],
                "last_event_at": row["last_event_at"],
                "segment_progress": segment_progress,
                "comment_backfill_progress": comment_backfill_progress,
            }
        )
    return tasks


def fetch_tasks() -> tuple[list[dict[str, Any]], str]:
    try:
        tasks = api_json("GET", "/api/v1/tasks?include_payload=false", retries=2) or []
        source = "api"
    except Exception:
        tasks = _load_tasks_from_db()
        source = "db"
    filtered = [t for t in tasks if str(t.get("platform") or "").lower() in PLATFORMS]
    return filtered, source


def normalize_progress(raw: Any) -> dict[str, int]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "total_posts": int(raw.get("total_posts") or 0),
        "eligible_posts": int(raw.get("eligible_posts") or 0),
        "processed_posts": int(raw.get("processed_posts") or 0),
        "skipped_posts": int(raw.get("skipped_posts") or 0),
        "succeeded_posts": int(raw.get("succeeded_posts") or 0),
        "failed_posts": int(raw.get("failed_posts") or 0),
    }


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
        new_posts = max(0, count - int(prev_counts.get(tid, 0) or 0))
        new_replies = max(0, replies - int(prev_replies.get(tid, 0) or 0))
        total_posts += new_posts
        total_replies += new_replies
        by_platform[platform]["new_posts"] += new_posts
        by_platform[platform]["new_replies"] += new_replies
    return by_platform, total_posts, total_replies


def task_label(task: dict[str, Any]) -> str:
    tid = str(task.get("task_id") or "")
    platform = str(task.get("platform") or "")
    keyword = str(task.get("keyword") or "")
    short = tid[:8] if tid else "--"
    return f"{platform}:{keyword or short}#{short}"


def ensure_comment_backfill_tasks(tasks: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
    comment_tasks = [t for t in tasks if str(t.get("task_kind") or "") == "comment_backfill"]
    resumable = [t for t in comment_tasks if str(t.get("status") or "") in {"paused", "stopped", "failed"}]
    if not resumable:
        return [], [], []

    id_to_task = {str(t.get("task_id") or ""): t for t in resumable}
    payload = {"task_ids": list(id_to_task.keys())}
    resp = api_json("POST", "/api/v1/tasks/batch-resume", payload, retries=1) or {}

    resumed = [task_label(id_to_task[tid]) for tid in resp.get("resumed", []) if tid in id_to_task]
    already = [task_label(id_to_task[tid]) for tid in resp.get("already_running", []) if tid in id_to_task]
    failed = [task_label(id_to_task[tid]) for tid in resp.get("failed", []) if tid in id_to_task]

    # skipped 多半是巡检期间任务状态已变为 pending/running，不算坏事，单独不报失败。
    return resumed, already, failed


def summarize_comment_backfill(tasks: list[dict[str, Any]], prev_state: dict[str, Any]) -> tuple[str | None, dict[str, Any], list[str]]:
    comment_tasks = [t for t in tasks if str(t.get("task_kind") or "") == "comment_backfill"]
    if not comment_tasks:
        return None, {}, []

    status_counter = Counter(str(t.get("status") or "unknown") for t in comment_tasks)
    total_eligible = 0
    total_processed = 0
    total_succeeded = 0
    total_failed_posts = 0
    stale_labels: list[str] = []
    next_state: dict[str, Any] = {}

    for task in comment_tasks:
        tid = str(task.get("task_id") or "")
        status = str(task.get("status") or "")
        progress = normalize_progress(task.get("comment_backfill_progress"))
        replies = int(task.get("replies_fetched") or 0)
        total_eligible += progress["eligible_posts"]
        total_processed += progress["processed_posts"]
        total_succeeded += progress["succeeded_posts"]
        total_failed_posts += progress["failed_posts"]

        prev = prev_state.get(tid, {}) if isinstance(prev_state, dict) else {}
        prev_status = str(prev.get("status") or "")
        prev_processed = int(prev.get("processed_posts") or 0)
        prev_replies = int(prev.get("replies_fetched") or 0)
        stale_runs = int(prev.get("stale_runs") or 0)

        progressed = progress["processed_posts"] > prev_processed or replies > prev_replies
        if status in {"running", "pending"} and prev_status == status and not progressed:
            stale_runs += 1
        else:
            stale_runs = 0

        next_state[tid] = {
            "status": status,
            "processed_posts": progress["processed_posts"],
            "replies_fetched": replies,
            "stale_runs": stale_runs,
        }

        if status == "running" and stale_runs >= 2:
            stale_labels.append(task_label(task))

    summary = (
        f"评论补采任务 {len(comment_tasks)} 个"
        f"（done {status_counter.get('done', 0)} / running {status_counter.get('running', 0)} / pending {status_counter.get('pending', 0)}"
        f" / paused {status_counter.get('paused', 0)} / stopped {status_counter.get('stopped', 0)} / failed {status_counter.get('failed', 0)}），"
        f"累计处理 {total_processed}/{total_eligible} 条帖子，成功 {total_succeeded} 条，失败 {total_failed_posts} 条。"
    )
    return summary, next_state, stale_labels


def main() -> int:
    state = load_state()
    initial_tasks, initial_source = fetch_tasks()

    backfilled = set(state.get("comment_backfill_sources", []) or [])
    search_tasks = [t for t in initial_tasks if str(t.get("task_kind") or "search") == "search"]
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
                resp = api_json("POST", "/api/v1/comment-backfill/from-tasks", payload, retries=1)
                for source in (resp or {}).get("sources", []) or []:
                    if source.get("status") == "created" and source.get("source_task_id"):
                        sid = str(source["source_task_id"])
                        backfilled.add(sid)
                        backfill_created.append(f"{source.get('platform')}:{source.get('source_keyword') or sid[:8]}")
            except Exception as e:
                backfill_created.append(f"补采触发失败: {e}")

    tasks, tasks_source = fetch_tasks()
    resumed_backfills: list[str] = []
    already_running_backfills: list[str] = []
    failed_backfill_resumes: list[str] = []
    if tasks_source == "api":
        resumed_backfills, already_running_backfills, failed_backfill_resumes = ensure_comment_backfill_tasks(tasks)
        if resumed_backfills or already_running_backfills or failed_backfill_resumes:
            tasks, tasks_source = fetch_tasks()

    prev_counts = state.get("task_counts", {}) or {}
    prev_replies = state.get("task_replies", {}) or {}
    by_platform, total_new_posts, total_new_replies = summarize_platform(tasks, prev_counts, prev_replies)

    comment_summary, comment_state, stale_backfills = summarize_comment_backfill(
        tasks,
        state.get("comment_backfill_task_state", {}) or {},
    )

    # 重新按当前任务刷新搜索状态，避免本轮触发评论补采后状态过旧。
    search_tasks = [t for t in tasks if str(t.get("task_kind") or "search") == "search"]
    incomplete_search_tasks = [
        t for t in search_tasks
        if str(t.get("status") or "") not in {"done"} or not segment_done(t)
    ]

    state["task_counts"] = {str(t.get("task_id") or ""): int(t.get("result_count") or 0) for t in tasks}
    state["task_replies"] = {str(t.get("task_id") or ""): int(t.get("replies_fetched") or 0) for t in tasks}
    state["comment_backfill_sources"] = sorted(backfilled)
    state["comment_backfill_task_state"] = comment_state
    state["last_run_at"] = now_utc().isoformat()
    save_state(state)

    parts: list[str] = []
    parts.append(f"巡检完成：X {by_platform.get('x', {}).get('tasks', 0)} 个任务，微博 {by_platform.get('weibo', {}).get('tasks', 0)} 个任务。")
    parts.append(f"本轮新增帖子 {total_new_posts} 条，新增评论 {total_new_replies} 条。")
    if initial_source == "db" or tasks_source == "db":
        parts.append("本轮巡检读取任务状态时走了数据库兜底（接口响应偏慢），但监控仍然有效。")

    if comment_summary:
        parts.append(comment_summary)
    if resumed_backfills:
        parts.append("本轮已自动续跑评论补采：" + "；".join(resumed_backfills[:8]) + ("；…" if len(resumed_backfills) > 8 else ""))
    if already_running_backfills:
        parts.append("这些评论补采任务已在运行/排队：" + "；".join(already_running_backfills[:8]) + ("；…" if len(already_running_backfills) > 8 else ""))
    if failed_backfill_resumes:
        parts.append("以下评论补采任务自动续跑失败：" + "；".join(failed_backfill_resumes[:8]) + ("；…" if len(failed_backfill_resumes) > 8 else ""))
    if stale_backfills:
        parts.append("疑似长时间无进展的评论补采任务：" + "；".join(stale_backfills[:6]) + ("；…" if len(stale_backfills) > 6 else ""))

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
