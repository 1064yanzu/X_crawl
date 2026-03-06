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


def _default_segment_progress() -> dict:
    return {
        "enabled": False,
        "total_segments": 0,
        "completed_segments": 0,
        "current_segment_index": 0,
        "current_since": None,
        "current_until": None,
    }


def _make_preview(tweets: list[dict]) -> list[dict]:
    from config import settings
    n = settings.crawler_preview_count
    return tweets[-n:] if len(tweets) > n else list(tweets)


def _get_scheduler():
    from api.services.task_scheduler import scheduler
    return scheduler


def _get_runtime_metrics(task_id: str, fallback: Optional[dict] = None) -> dict:
    fallback = fallback or {}
    try:
        from crawler.runtime_metrics import get_metrics

        live = get_metrics(task_id)
        if any(v for v in live.values()):
            return live
    except Exception:
        pass
    return dict(fallback)


def _get_resource_metrics() -> dict:
    try:
        from crawler.resource_guard import get_resource_metrics

        return get_resource_metrics()
    except Exception:
        return {}


def _summarize_tweets(tweets: list[dict]) -> tuple[int, dict]:
    try:
        from api.services.task_insights import summarize_tweets

        return summarize_tweets(tweets)
    except Exception as e:
        logger.warning(f"_summarize_tweets 异常: {e}", exc_info=True)
        return 0, {}


def _queue_positions() -> dict[str, int]:
    try:
        queued = _get_scheduler().queued_task_ids()
    except Exception:
        return {}
    return {tid: idx + 1 for idx, tid in enumerate(queued)}


def _decorate_task_runtime(task: dict, *, queue_position: Optional[int]) -> dict:
    from crawler import telemetry

    task_id = task.get("task_id", "")
    runtime_metrics = _get_runtime_metrics(task_id, fallback=task.get("runtime_metrics", {}))
    live_metrics = telemetry.get_snapshot(task_id, queue_position=queue_position)
    live_metrics.update(runtime_metrics)
    live_metrics.update(_get_resource_metrics())
    try:
        sched = _get_scheduler()
        live_metrics["queue_size"] = sched.queue_size()
        live_metrics["running_count"] = sched.running_count()
        live_metrics["effective_worker_limit"] = sched.effective_worker_limit()
    except Exception:
        pass

    enriched = copy.deepcopy(task)
    enriched["runtime_metrics"] = runtime_metrics
    enriched["live_metrics"] = live_metrics
    enriched["latest_action"] = telemetry.get_latest_action(task_id)
    enriched["queue_position"] = queue_position
    return enriched


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
        from crawler import telemetry

        with _tasks_lock:
            for task in history:
                tid = task["task_id"]
                task.setdefault("risk_state", "none")
                task.setdefault("quality_state", "complete")
                task.setdefault("runtime_metrics", {})
                task.setdefault("last_event_at", task.get("created_at"))
                task.setdefault("time_coverage", {})
                task.setdefault("segment_progress", _default_segment_progress())
                task.setdefault("platform", "x")
                task.setdefault("start_date", None)
                task.setdefault("end_date", None)

                if task["status"] in ("running", "pending", "paused"):
                    task["status"] = "stopped"
                    task["quality_state"] = "interrupted"
                    task["finished_at"] = _now_iso()
                    _touch(task)
                    db.save_task(task)
                _tasks[tid] = task
                telemetry.init_task(
                    tid,
                    status=task.get("status", "pending"),
                    phase=task.get("crawl_phase", ""),
                )

        _db_initialized = True
        from config import apply_user_settings
        apply_user_settings()
        try:
            from api.services.performance_tuner import apply_startup_performance_tuning

            apply_startup_performance_tuning()
        except Exception as e:
            logger.warning(f"启动性能调优失败（忽略继续运行）: {e}")


try:
    _ensure_db()
except Exception as e:  # pragma: no cover - 启动容错
    logger.warning(f"任务数据库初始化失败（将在首次操作时重试）: {e}")


def _persist(task_id: str, *, force: bool = False, full: bool = False) -> None:
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
        if full:
            _get_db().save_task(snapshot)
        else:
            _get_db().save_task_summary(snapshot)
    except Exception as e:
        logger.error(f"持久化任务失败 task_id={task_id}: {e}")


def _persist_force(task_id: str) -> None:
    _persist(task_id, force=True, full=True)


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
    from crawler import telemetry

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task or task["status"] not in ("running",):
            return False
        task["status"] = "paused"
        _touch(task)
    send_signal(task_id, "pause")
    telemetry.record_event(task_id, "task_paused", status="paused", phase="任务已暂停，等待继续信号")
    _persist_force(task_id)
    return True


def resume_task(task_id: str) -> bool:
    _ensure_db()
    from crawler import telemetry

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
    telemetry.record_event(task_id, "task_resumed", status="running", phase="任务已恢复运行")
    _persist_force(task_id)
    return True


def resume_finished_task(task_id: str) -> bool:
    _ensure_db()
    from crawler import telemetry

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
    telemetry.record_event(task_id, "task_requeued", status="pending", phase="已加入调度队列，等待执行...")
    _persist_force(task_id)
    return True


def stop_task(task_id: str) -> bool:
    _ensure_db()
    from crawler import telemetry

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task or task["status"] not in ("running", "paused", "pending"):
            return False
    send_signal(task_id, "stop")
    telemetry.record_event(task_id, "task_stop_requested", status=task.get("status"), phase="收到终止信号，等待安全退出")
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
    platform: str = "x",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    _ensure_db()
    from crawler import telemetry

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
            "time_coverage": existing.get("time_coverage", {}),
            "segment_progress": existing.get("segment_progress", _default_segment_progress()),
            "last_event_at": _now_iso(),
            "resumed": False,
            "fetch_replies": fetch_replies,
            "max_replies_per_tweet": max_replies_per_tweet,
            "reply_depth": reply_depth,
            "crawl_strategy": crawl_strategy,
            "platform": platform,
            "start_date": start_date,
            "end_date": end_date,
            "replies_fetched": existing.get("replies_fetched", 0),
            "tweets": existing.get("tweets", []),
            "preview_tweets": existing.get("preview_tweets", []),
            "crawl_phase": "已加入调度队列，等待执行...",
        }
    send_signal(tid, "run")
    telemetry.init_task(tid, status="pending", phase="已加入调度队列，等待执行...")
    telemetry.record_event(
        tid,
        "task_created",
        status="pending",
        phase="已加入调度队列，等待执行...",
        meta={
            "keyword": keyword,
            "product": product,
            "fetch_replies": fetch_replies,
            "crawl_strategy": crawl_strategy,
        },
    )
    _persist_force(tid)
    logger.info(f"任务已创建/重置: task_id={tid}, strategy={crawl_strategy}, fetch_replies={fetch_replies}")
    return tid


def get_task(task_id: str) -> Optional[dict]:
    _ensure_db()
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return None
        snapshot = copy.deepcopy(task)
    queue_position = _queue_positions().get(task_id) if snapshot.get("status") == "pending" else None
    return _decorate_task_runtime(snapshot, queue_position=queue_position)


def list_tasks() -> list[dict]:
    _ensure_db()
    with _tasks_lock:
        tasks = [copy.deepcopy(t) for t in _tasks.values()]
    queue_positions = _queue_positions()
    tasks = [
        _decorate_task_runtime(
            t,
            queue_position=queue_positions.get(t.get("task_id", "")) if t.get("status") == "pending" else None,
        )
        for t in tasks
    ]
    tasks.sort(key=lambda t: t["created_at"], reverse=True)
    return tasks


def get_task_events(task_id: str, *, after_id: int = 0, limit: int = 120) -> list[dict]:
    from crawler import telemetry

    return telemetry.get_events_since(task_id, after_id=after_id, limit=limit)


def update_task_status(task_id: str, status: TaskStatus) -> None:
    from crawler import telemetry

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
        phase = task.get("crawl_phase", "")
        risk_state = task.get("risk_state")
    telemetry.record_event(task_id, "task_status", status=status, phase=phase, risk_state=risk_state)
    _persist_force(task_id)


def update_task_phase(task_id: str, phase: str) -> None:
    from crawler import telemetry

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["crawl_phase"] = phase
        _touch(task)
        status = task.get("status")
        risk_state = task.get("risk_state")
        page = task.get("current_page")
    telemetry.record_event(
        task_id,
        "task_phase",
        phase=phase,
        status=status,
        risk_state=risk_state,
        page=page,
    )


def update_task_segment_progress(task_id: str, progress: Optional[dict]) -> None:
    if progress is None:
        progress = _default_segment_progress()
    merged = {**_default_segment_progress(), **progress}
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["segment_progress"] = merged
        _touch(task)
    _persist(task_id)


def update_task_progress(task_id: str, current_page: int, tweets_so_far: list[dict]) -> None:
    from crawler import telemetry

    replies_fetched, coverage = _summarize_tweets(tweets_so_far)

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        prev_result = int(task.get("result_count", 0))
        prev_replies = int(task.get("replies_fetched", 0))
        task.update({
            "current_page": current_page,
            "result_count": len(tweets_so_far),
            "replies_fetched": replies_fetched,
            "tweets": tweets_so_far,
            "preview_tweets": _make_preview(tweets_so_far),
            "time_coverage": coverage,
        })
        _touch(task)
        delta_tweets = max(0, len(tweets_so_far) - prev_result)
        delta_replies = max(0, replies_fetched - prev_replies)
        phase = task.get("crawl_phase", "")
        status = task.get("status")
        risk_state = task.get("risk_state")
    telemetry.record_event(
        task_id,
        "search_progress",
        phase=phase,
        page=current_page,
        delta_tweets=delta_tweets,
        delta_replies=delta_replies,
        status=status,
        risk_state=risk_state,
        meta={"result_count": len(tweets_so_far), "replies_fetched": replies_fetched},
    )
    _persist(task_id)


def update_preview_tweets(task_id: str, current_page: int, tweets_for_preview: list[dict]) -> None:
    """更新预览推文 + 同步 tweets 字段并触发节流持久化，确保中断时数据不丢失。"""
    from crawler import telemetry

    replies_fetched, coverage = _summarize_tweets(tweets_for_preview)

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        prev_result = int(task.get("result_count", 0))
        task.update({
            "current_page": current_page,
            "result_count": len(tweets_for_preview),
            "tweets": tweets_for_preview,
            "preview_tweets": _make_preview(tweets_for_preview),
            "replies_fetched": replies_fetched,
            "time_coverage": coverage,
        })
        _touch(task)
        delta_tweets = max(0, len(tweets_for_preview) - prev_result)
        phase = task.get("crawl_phase", "")
        status = task.get("status")
        risk_state = task.get("risk_state")
    telemetry.record_event(
        task_id,
        "preview_progress",
        phase=phase,
        page=current_page,
        delta_tweets=delta_tweets,
        status=status,
        risk_state=risk_state,
        meta={"preview_count": len(tweets_for_preview)},
    )
    _persist(task_id)


def update_task_replies_progress(task_id: str, tweet_id: str, reply_count: int) -> None:
    from crawler import telemetry

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["replies_fetched"] = task.get("replies_fetched", 0) + reply_count
        _touch(task)
        phase = task.get("crawl_phase", "")
        status = task.get("status")
        risk_state = task.get("risk_state")
        page = task.get("current_page")
    telemetry.record_event(
        task_id,
        "reply_progress",
        phase=phase,
        page=page,
        delta_replies=max(0, int(reply_count)),
        status=status,
        risk_state=risk_state,
        meta={"tweet_id": tweet_id},
    )
    _persist(task_id)


def update_task_result(
    task_id: str,
    tweets: list[dict],
    resumed: bool = False,
    replies_fetched: int = 0,
    quality_state: str = "complete",
    runtime_metrics: Optional[dict] = None,
) -> None:
    from crawler import telemetry

    computed_replies, coverage = _summarize_tweets(tweets)
    final_replies = max(int(replies_fetched), int(computed_replies))

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
            "replies_fetched": final_replies,
            "time_coverage": coverage,
        })
        _touch(task)
        phase = task.get("crawl_phase", "")
    clear_signal(task_id)
    telemetry.record_event(
        task_id,
        "task_done",
        status="done",
        phase=phase,
        delta_tweets=max(0, len(tweets)),
        delta_replies=max(0, final_replies),
        risk_state="none",
        meta={"quality_state": quality_state},
    )
    _persist_force(task_id)


def update_task_stopped(task_id: str, tweets_so_far: list[dict], runtime_metrics: Optional[dict] = None) -> None:
    from crawler import telemetry

    replies_fetched, coverage = _summarize_tweets(tweets_so_far)

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
            "replies_fetched": replies_fetched,
            "time_coverage": coverage,
        })
        _touch(task)
        phase = task.get("crawl_phase", "")
    clear_signal(task_id)
    telemetry.record_event(
        task_id,
        "task_stopped",
        status="stopped",
        phase=phase,
        meta={"result_count": len(tweets_so_far)},
    )
    _persist_force(task_id)


def update_task_error(task_id: str, error: str, runtime_metrics: Optional[dict] = None) -> None:
    from crawler import telemetry

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
        phase = task.get("crawl_phase", "")
    clear_signal(task_id)
    telemetry.record_event(
        task_id,
        "task_failed",
        status="failed",
        phase=phase,
        meta={"error": error[:240]},
    )
    _persist_force(task_id)


def update_task_risk_paused(
    task_id: str,
    risk_state: RiskState,
    phase: str,
    runtime_metrics: Optional[dict] = None,
) -> None:
    from crawler import telemetry

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
    telemetry.record_event(
        task_id,
        "task_risk_paused",
        status="paused",
        phase=phase,
        risk_state=risk_state,
    )
    _persist_force(task_id)


def delete_task(task_id: str) -> bool:
    from crawler import telemetry

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
    telemetry.clear_task(task_id)

    try:
        _get_db().delete_task(task_id)
    except Exception as e:
        logger.error(f"从数据库删除任务失败 task_id={task_id}: {e}")
    return True
