from __future__ import annotations

import copy
import logging
import threading
import time
from datetime import datetime, timezone

from config import settings

logger = logging.getLogger(__name__)

_watchdog_lock = threading.Lock()
_watchdog_last_run = 0.0
_watchdog_local = threading.local()


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _watchdog_enabled() -> bool:
    return bool(getattr(settings, "crawler_active_task_watchdog_enabled", True))


def _watchdog_interval_sec() -> float:
    return max(5.0, float(getattr(settings, "crawler_active_task_watchdog_interval_sec", 30.0)))


def _stale_timeout_sec() -> float:
    return max(60.0, float(getattr(settings, "crawler_active_task_stale_timeout_sec", 900.0)))


def _is_stale_comment_backfill(task: dict, *, now: datetime) -> tuple[bool, float]:
    if str(task.get("task_kind") or "") != "comment_backfill":
        return False, 0.0
    status = str(task.get("status") or "")
    # pending 的任务只是在调度队列中排队等待，没有运行线程，不应被判定为 stale
    if status != "running":
        return False, 0.0

    heartbeat = _parse_iso(task.get("last_event_at")) or _parse_iso(task.get("created_at"))
    if heartbeat is None:
        return False, 0.0

    idle_sec = max(0.0, (now - heartbeat).total_seconds())
    return idle_sec >= _stale_timeout_sec(), idle_sec


def maybe_heal_stale_active_tasks(*, force: bool = False) -> None:
    global _watchdog_last_run

    if not _watchdog_enabled():
        return
    if getattr(_watchdog_local, "running", False):
        return

    now_mono = time.monotonic()
    if not force and now_mono - _watchdog_last_run < _watchdog_interval_sec():
        return
    if not _watchdog_lock.acquire(blocking=False):
        return

    _watchdog_local.running = True
    try:
        _watchdog_last_run = now_mono

        from api.services import task_manager

        now = datetime.now(timezone.utc)
        candidates: list[tuple[dict, float]] = []
        with task_manager._tasks_lock:
            for task in task_manager._tasks.values():
                snapshot = copy.deepcopy(task)
                stale, idle_sec = _is_stale_comment_backfill(snapshot, now=now)
                if stale:
                    candidates.append((snapshot, idle_sec))

        for task, idle_sec in candidates:
            _heal_stale_task(task, idle_sec=idle_sec)
    finally:
        _watchdog_local.running = False
        _watchdog_lock.release()


def _heal_stale_task(task: dict, *, idle_sec: float) -> None:
    from api.services import crawl_service, task_manager, task_queue_manager
    from api.services.task_scheduler import scheduler

    task_id = str(task.get("task_id") or "")
    if not task_id:
        return

    latest = task_manager._get_task_summary_snapshot(task_id)
    if not latest:
        return

    stale, current_idle_sec = _is_stale_comment_backfill(latest, now=datetime.now(timezone.utc))
    if not stale:
        return

    idle_minutes = max(1, int(round(current_idle_sec / 60.0)))
    queue_id = str(latest.get("queue_id") or "").strip() or None
    logger.warning(
        "检测到长时间无进展的评论补采任务，准备自动重排: task_id=%s idle=%dmin status=%s queue=%s thread_alive=%s",
        task_id[:8],
        idle_minutes,
        latest.get("status"),
        (queue_id or "-")[:8],
        task_manager.is_thread_alive(task_id),
    )

    task_manager.send_signal(task_id, "stop")
    task_manager.clear_thread(task_id)
    scheduler.mark_done(task_id)

    tweets_so_far = task_manager._get_task_result_snapshot(task_id, load=True)
    task_manager.update_task_phase(task_id, f"任务长时间无进展（约 {idle_minutes} 分钟），已自动重新排队")
    task_manager.update_task_stopped(task_id, tweets_so_far)

    # 更新队列中所有 pending 任务的 heartbeat，防止 watchdog 在下个周期
    # 再次误判它们为 stale（它们的 last_event_at 可能是很久以前创建时的时间戳）
    if queue_id:
        _touch_queue_pending_tasks(queue_id, task_manager)

    if queue_id:
        try:
            task_queue_manager.resume_queue(queue_id)
            return
        except Exception as exc:
            logger.error("自动恢复评论补采队列失败: queue=%s, error=%s", queue_id[:8], exc, exc_info=True)

    if task_manager.resume_finished_task(task_id):
        refreshed = task_manager._get_task_summary_snapshot(task_id) or latest
        crawl_service.start_crawler_thread(task_id, refreshed, force_new_browser=True)


def _touch_queue_pending_tasks(queue_id: str, task_manager) -> None:
    """刷新队列中所有 pending/running 任务的 heartbeat，避免 watchdog 误判。"""
    from api.services import task_queue_manager

    try:
        with task_queue_manager._lock:
            q = task_queue_manager._queues.get(queue_id)
            if not q:
                return
            tids = list(q.get("task_ids", []))
    except Exception:
        return

    with task_manager._tasks_lock:
        for tid in tids:
            t = task_manager._tasks.get(tid)
            if t and str(t.get("status") or "") in {"pending", "running"}:
                t["last_event_at"] = datetime.now(timezone.utc).isoformat()
                logger.debug("watchdog 刷新 heartbeat: task=%s", tid[:8])
