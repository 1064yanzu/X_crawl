"""
任务管理器（线程安全 + 节流持久化 + 质量指标字段）。
"""
from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from api.schemas.task import RiskState, TaskStatus

logger = logging.getLogger(__name__)

_tasks: dict[str, dict] = {}
_tasks_lock = threading.RLock()

_task_signals: dict[str, str] = {}
_signal_lock = threading.Lock()

_task_threads: dict[str, threading.Thread] = {}
_threads_lock = threading.RLock()

_persist_mark: dict[str, float] = {}
_persist_mark_lock = threading.Lock()
_PERSIST_MIN_INTERVAL_SEC = 0.4

_db_initialized = False
_db_lock = threading.Lock()


def _get_db():
    from api.services import task_db
    return task_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _touch(task: dict) -> None:
    task["last_event_at"] = _now_iso()


def _make_preview(tweets: list[dict]) -> list[dict]:
    from config import settings
    n = settings.crawler_preview_count
    return tweets[-n:] if len(tweets) > n else list(tweets)


def _ensure_db() -> None:
    global _db_initialized
    if _db_initialized:
        return

    with _db_lock:
        if _db_initialized:
            return

        from config import settings

        db = _get_db()
        db.init_db(settings.tasks_db_path)
        history = db.load_all_tasks()

        with _tasks_lock:
            for task in history:
                tid = task["task_id"]
                task.setdefault("risk_state", "none")
                task.setdefault("quality_state", "complete")
                task.setdefault("runtime_metrics", {})
                task.setdefault("last_event_at", task.get("created_at"))

                if task["status"] in ("running", "pending", "paused"):
                    task["status"] = "stopped"
                    task["quality_state"] = "interrupted"
                    task["finished_at"] = _now_iso()
                    _touch(task)
                    db.save_task(task)
                _tasks[tid] = task

        _db_initialized = True
        from config import apply_user_settings
        apply_user_settings()


try:
    _ensure_db()
except Exception as e:  # pragma: no cover - 启动容错
    logger.warning(f"任务数据库初始化失败（将在首次操作时重试）: {e}")


def _persist(task_id: str, *, force: bool = False) -> None:
    _ensure_db()
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        snapshot = copy.deepcopy(task)

    now = time.monotonic()
    with _persist_mark_lock:
        last = _persist_mark.get(task_id, 0.0)
        if not force and now - last < _PERSIST_MIN_INTERVAL_SEC:
            return
        _persist_mark[task_id] = now

    try:
        _get_db().save_task(snapshot)
    except Exception as e:
        logger.error(f"持久化任务失败 task_id={task_id}: {e}")


def _persist_force(task_id: str) -> None:
    _persist(task_id, force=True)


def send_signal(task_id: str, signal: str) -> None:
    with _signal_lock:
        _task_signals[task_id] = signal
    logger.info(f"信号已发送: task_id={task_id}, signal={signal}")


def get_signal(task_id: str | None) -> str:
    if not task_id:
        return "run"
    with _signal_lock:
        return _task_signals.get(task_id, "run")


def clear_signal(task_id: str) -> None:
    with _signal_lock:
        _task_signals.pop(task_id, None)


def register_thread(task_id: str, thread: threading.Thread) -> None:
    with _threads_lock:
        _task_threads[task_id] = thread


def is_thread_alive(task_id: str) -> bool:
    with _threads_lock:
        thread = _task_threads.get(task_id)
    return bool(thread and thread.is_alive())


def clear_thread(task_id: str) -> None:
    with _threads_lock:
        _task_threads.pop(task_id, None)


def pause_task(task_id: str) -> bool:
    _ensure_db()
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task or task["status"] not in ("running",):
            return False
        task["status"] = "paused"
        _touch(task)
    send_signal(task_id, "pause")
    _persist_force(task_id)
    return True


def resume_task(task_id: str) -> bool:
    _ensure_db()
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        current_signal = get_signal(task_id)
        if task["status"] not in ("paused",) and current_signal != "pause":
            return False
        task["status"] = "running"
        task["risk_state"] = "none"
        _touch(task)
    send_signal(task_id, "run")
    _persist_force(task_id)
    return True


def resume_finished_task(task_id: str) -> bool:
    _ensure_db()
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        if task["status"] not in ("done", "stopped", "failed"):
            return False
        task["status"] = "pending"
        task["finished_at"] = None
        task["error"] = None
        task["risk_state"] = "none"
        task["quality_state"] = "complete"
        task["crawl_phase"] = "已加入调度队列，等待执行..."
        _touch(task)
    send_signal(task_id, "run")
    _persist_force(task_id)
    return True


def stop_task(task_id: str) -> bool:
    _ensure_db()
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task or task["status"] not in ("running", "paused", "pending"):
            return False
    send_signal(task_id, "stop")
    return True


def count_active_tasks() -> int:
    _ensure_db()
    with _tasks_lock:
        return sum(1 for task in _tasks.values() if task.get("status") in ("pending", "running"))


def create_task(
    keyword: str,
    max_count: int,
    product: str,
    task_id: Optional[str] = None,
    fetch_replies: bool = False,
    max_replies_per_tweet: int = 20,
    reply_depth: int = 2,
    crawl_strategy: str = "bfs",
) -> str:
    _ensure_db()
    tid = task_id or str(uuid.uuid4())

    if tid in _tasks and is_thread_alive(tid):
        logger.warning(f"任务 {tid} 的爬虫线程仍在运行，忽略重复创建")
        return tid

    with _tasks_lock:
        existing = _tasks.get(tid, {})
        _tasks[tid] = {
            "task_id": tid,
            "status": "pending",
            "keyword": keyword,
            "product": product,
            "max_count": max_count,
            "result_count": existing.get("result_count", 0),
            "current_page": existing.get("current_page", 0),
            "created_at": existing.get("created_at") or _now_iso(),
            "finished_at": None,
            "error": None,
            "risk_state": "none",
            "quality_state": "complete",
            "runtime_metrics": existing.get("runtime_metrics", {}),
            "last_event_at": _now_iso(),
            "resumed": False,
            "fetch_replies": fetch_replies,
            "max_replies_per_tweet": max_replies_per_tweet,
            "reply_depth": reply_depth,
            "crawl_strategy": crawl_strategy,
            "replies_fetched": existing.get("replies_fetched", 0),
            "tweets": existing.get("tweets", []),
            "preview_tweets": existing.get("preview_tweets", []),
            "crawl_phase": "已加入调度队列，等待执行...",
        }
    send_signal(tid, "run")
    _persist_force(tid)
    logger.info(f"任务已创建/重置: task_id={tid}, strategy={crawl_strategy}, fetch_replies={fetch_replies}")
    return tid


def get_task(task_id: str) -> Optional[dict]:
    _ensure_db()
    with _tasks_lock:
        task = _tasks.get(task_id)
        return copy.deepcopy(task) if task else None


def list_tasks() -> list[dict]:
    _ensure_db()
    with _tasks_lock:
        tasks = [copy.deepcopy(t) for t in _tasks.values()]
    tasks.sort(key=lambda t: t["created_at"], reverse=True)
    return tasks


def update_task_status(task_id: str, status: TaskStatus) -> None:
    with _tasks_lock:
        if task_id not in _tasks:
            return
        task = _tasks[task_id]
        task["status"] = status
        if status in ("running", "done", "stopped"):
            task["risk_state"] = "none"
        if status in ("done", "failed", "stopped"):
            task["finished_at"] = _now_iso()
            clear_signal(task_id)
        _touch(task)
    _persist_force(task_id)


def update_task_phase(task_id: str, phase: str) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["crawl_phase"] = phase
        _touch(task)


def update_task_progress(task_id: str, current_page: int, tweets_so_far: list[dict]) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        replies_fetched = sum(len(t.get("replies", [])) for t in tweets_so_far)
        task.update({
            "current_page": current_page,
            "result_count": len(tweets_so_far),
            "replies_fetched": replies_fetched,
            "tweets": tweets_so_far,
            "preview_tweets": _make_preview(tweets_so_far),
        })
        _touch(task)
    _persist(task_id)


def update_preview_tweets(task_id: str, current_page: int, tweets_for_preview: list[dict]) -> None:
    """更新预览推文 + 同步 tweets 字段并触发节流持久化，确保中断时数据不丢失。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task.update({
            "current_page": current_page,
            "result_count": len(tweets_for_preview),
            "tweets": tweets_for_preview,
            "preview_tweets": _make_preview(tweets_for_preview),
        })
        _touch(task)
    _persist(task_id)


def update_task_replies_progress(task_id: str, tweet_id: str, reply_count: int) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["replies_fetched"] = task.get("replies_fetched", 0) + reply_count
        _touch(task)
    _persist(task_id)


def update_task_result(
    task_id: str,
    tweets: list[dict],
    resumed: bool = False,
    replies_fetched: int = 0,
    quality_state: str = "complete",
    runtime_metrics: Optional[dict] = None,
) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task.update({
            "tweets": tweets,
            "preview_tweets": _make_preview(tweets),
            "result_count": len(tweets),
            "status": "done",
            "finished_at": _now_iso(),
            "risk_state": "none",
            "quality_state": quality_state,
            "runtime_metrics": runtime_metrics or {},
            "resumed": resumed,
            "replies_fetched": replies_fetched,
        })
        _touch(task)
    clear_signal(task_id)
    _persist_force(task_id)


def update_task_stopped(task_id: str, tweets_so_far: list[dict], runtime_metrics: Optional[dict] = None) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task.update({
            "tweets": tweets_so_far,
            "preview_tweets": _make_preview(tweets_so_far),
            "result_count": len(tweets_so_far),
            "status": "stopped",
            "quality_state": "interrupted",
            "runtime_metrics": runtime_metrics or {},
            "finished_at": _now_iso(),
            "risk_state": "none",
        })
        _touch(task)
    clear_signal(task_id)
    _persist_force(task_id)


def update_task_error(task_id: str, error: str, runtime_metrics: Optional[dict] = None) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task.update({
            "status": "failed",
            "quality_state": "interrupted",
            "runtime_metrics": runtime_metrics or {},
            "error": error,
            "finished_at": _now_iso(),
        })
        _touch(task)
    clear_signal(task_id)
    _persist_force(task_id)


def update_task_risk_paused(
    task_id: str,
    risk_state: RiskState,
    phase: str,
    runtime_metrics: Optional[dict] = None,
) -> None:
    with _tasks_lock:
        if task_id not in _tasks:
            return
        task = _tasks[task_id]
        task.update({
            "status": "paused",
            "risk_state": risk_state,
            "quality_state": "partial",
            "runtime_metrics": runtime_metrics or task.get("runtime_metrics", {}),
            "crawl_phase": phase,
        })
        _touch(task)
    send_signal(task_id, "pause")
    _persist_force(task_id)


def delete_task(task_id: str) -> bool:
    removed = False
    with _tasks_lock:
        if task_id in _tasks:
            del _tasks[task_id]
            removed = True
    if not removed:
        return False

    clear_signal(task_id)
    clear_thread(task_id)
    with _persist_mark_lock:
        _persist_mark.pop(task_id, None)

    try:
        _get_db().delete_task(task_id)
    except Exception as e:
        logger.error(f"从数据库删除任务失败 task_id={task_id}: {e}")
    return True

