from __future__ import annotations

import copy
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {"done", "failed", "stopped"}
_ACTIVE_STATUSES = {"running", "paused"}

_queues: dict[str, dict] = {}
_task_to_queue: dict[str, str] = {}
_lock = threading.RLock()
_loaded = False
_load_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_db():
    from api.services import task_db

    return task_db


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return

    with _load_lock:
        if _loaded:
            return

        from config import settings

        db = _get_db()
        db.init_db(settings.tasks_db_path)
        queues = db.load_task_queues()

        with _lock:
            _queues.clear()
            _task_to_queue.clear()
            for queue in queues:
                queue_id = queue.get("queue_id")
                if not queue_id:
                    continue
                queue.setdefault("name", f"任务队列 {queue_id[:8]}")
                queue.setdefault("status", "paused")
                queue.setdefault("created_at", _now_iso())
                queue.setdefault("started_at", None)
                queue.setdefault("finished_at", None)
                queue.setdefault("current_task_id", None)
                queue.setdefault("task_ids", [])
                queue.setdefault("started_task_ids", [])
                _restore_queue_waiting_tasks(queue)
                if queue.get("status") == "running":
                    queue["status"] = "paused"
                _queues[queue_id] = queue
                for task_id in queue["task_ids"]:
                    _task_to_queue[task_id] = queue_id
        _loaded = True


def _restore_queue_waiting_tasks(queue: dict) -> None:
    from api.services import task_manager

    task_ids = [task_id for task_id in queue.get("task_ids", []) if task_id]
    started = set(queue.get("started_task_ids", []))
    total = len(task_ids)

    for index, task_id in enumerate(task_ids, start=1):
        if task_id in started:
            continue
        task = task_manager.get_task_summary(task_id)
        if not task:
            continue
        if task.get("status") == "stopped" and int(task.get("result_count", 0)) == 0:
            task_manager.restore_waiting_task(
                task_id,
                f"任务队列等待中（{index}/{total}），等待前序任务完成",
            )

    if queue.get("current_task_id"):
        return

    for task_id in reversed(queue.get("started_task_ids", [])):
        task = task_manager.get_task_summary(task_id)
        if task:
            queue["current_task_id"] = task_id
            return

    if task_ids:
        queue["current_task_id"] = task_ids[0]


def _persist_queue(queue: dict) -> None:
    _get_db().save_task_queue(copy.deepcopy(queue))


def _build_queue_view(queue: dict) -> dict:
    from api.services import task_manager

    summaries: list[dict] = []
    completed_tasks = 0
    running_tasks = 0
    pending_tasks = 0
    failed_tasks = 0
    stopped_tasks = 0

    for task_id in queue.get("task_ids", []):
        task = task_manager.get_task_summary(task_id)
        if not task:
            continue
        summaries.append(task)
        status = task.get("status")
        if status == "done":
            completed_tasks += 1
        elif status == "failed":
            failed_tasks += 1
        elif status == "stopped":
            stopped_tasks += 1
        elif status in _ACTIVE_STATUSES:
            running_tasks += 1
        elif status == "pending":
            pending_tasks += 1

    return {
        "queue_id": queue["queue_id"],
        "name": queue.get("name") or f"任务队列 {queue['queue_id'][:8]}",
        "status": queue.get("status", "paused"),
        "created_at": queue.get("created_at"),
        "started_at": queue.get("started_at"),
        "finished_at": queue.get("finished_at"),
        "current_task_id": queue.get("current_task_id"),
        "total_tasks": len(queue.get("task_ids", [])),
        "completed_tasks": completed_tasks,
        "running_tasks": running_tasks,
        "pending_tasks": pending_tasks,
        "failed_tasks": failed_tasks,
        "stopped_tasks": stopped_tasks,
        "tasks": summaries,
    }


def create_queue(*, name: Optional[str], task_payloads: list[dict]) -> dict:
    _ensure_loaded()

    from api.services import crawl_service, task_manager

    total = len(task_payloads)
    queue_id = str(uuid.uuid4())
    queue_name = (name or "").strip() or f"任务队列 {queue_id[:8]}"
    task_ids: list[str] = []

    for index, payload in enumerate(task_payloads, start=1):
        task_id = task_manager.create_task(
            keyword=payload["keyword"],
            max_count=payload.get("max_count", 0),
            product=payload.get("product", "Top"),
            fetch_replies=payload.get("fetch_replies", False),
            max_replies_per_tweet=payload.get("max_replies_per_tweet", 0),
            reply_depth=payload.get("reply_depth", 2),
            crawl_strategy=payload.get("crawl_strategy", "dfs"),
            platform=payload.get("platform", "x"),
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            task_kind=payload.get("task_kind", "search"),
            source_file_name=payload.get("source_file_name"),
            source_task_id=payload.get("source_task_id"),
            queue_id=queue_id,
            queue_name=queue_name,
            queue_order=index,
            queue_total=total,
            comment_backfill_progress=payload.get("comment_backfill_progress"),
        )
        seed_tweets = payload.get("seed_tweets")
        if isinstance(seed_tweets, list) and seed_tweets:
            task_manager.set_task_seed_tweets(task_id, copy.deepcopy(seed_tweets), current_page=0)
        task_manager.update_task_phase(task_id, f"任务已创建（{index}/{total}），正在进入调度队列...")
        task_ids.append(task_id)

    queue = {
        "queue_id": queue_id,
        "name": queue_name,
        "status": "running",
        "created_at": _now_iso(),
        "started_at": _now_iso(),
        "finished_at": None,
        "current_task_id": task_ids[0] if task_ids else None,
        "task_ids": task_ids,
        "started_task_ids": list(task_ids),
    }

    with _lock:
        _queues[queue_id] = queue
        for task_id in task_ids:
            _task_to_queue[task_id] = queue_id
        _persist_queue(queue)

    # 将所有任务一次性提交给调度器，调度器自己根据并发上限控制执行顺序
    for task_id in task_ids:
        task_summary = task_manager.get_task_summary(task_id)
        if task_summary:
            crawl_service.start_crawler_thread(task_id, task_summary, resume=False)
    return _build_queue_view(queue)


def get_queue(queue_id: str) -> Optional[dict]:
    _ensure_loaded()
    with _lock:
        queue = copy.deepcopy(_queues.get(queue_id))
    if not queue:
        return None
    return _build_queue_view(queue)


def list_queues() -> list[dict]:
    _ensure_loaded()
    with _lock:
        queues = [copy.deepcopy(queue) for queue in _queues.values()]
    views = [_build_queue_view(queue) for queue in queues]
    views.sort(key=lambda item: item["created_at"], reverse=True)
    return views


def can_resume_task(task_id: str) -> tuple[bool, Optional[str], bool]:
    """检查任务是否可以恢复。

    Returns:
        (can_resume, reason, needs_queue): 第三个值表示是否需要排队等待。
        并发模式下 needs_queue 始终为 False——交给调度器控制并发。
    """
    _ensure_loaded()

    from api.services import task_manager
    from config import settings

    task = task_manager.get_task_summary(task_id)
    if not task:
        return False, "任务不存在", False

    queue_id = task.get("queue_id")
    if not queue_id:
        return True, None, False

    with _lock:
        queue = copy.deepcopy(_queues.get(queue_id))
    if not queue:
        return True, None, False

    task_ids = queue.get("task_ids", [])
    if task_id not in task_ids:
        return True, None, False

    # 并发模式（并发数 > 1）：直接让调度器决定，不在队列层面排队
    max_concurrent = int(settings.crawler_max_concurrent_tasks)
    if max_concurrent > 1:
        return True, None, False

    # 串行模式：保留原有逻辑，队列中有其他任务运行则排队
    current_task_id = queue.get("current_task_id")
    if current_task_id and current_task_id != task_id:
        current_task = task_manager.get_task_summary(current_task_id)
        if current_task and current_task.get("status") not in _TERMINAL_STATUSES:
            return True, None, True

    index = task_ids.index(task_id)
    for prev_task_id in task_ids[:index]:
        prev_task = task_manager.get_task_summary(prev_task_id)
        if prev_task and prev_task.get("status") not in _TERMINAL_STATUSES:
            return True, None, True

    return True, None, False


def mark_task_resuming(task_id: str) -> None:
    _ensure_loaded()

    from api.services import task_manager

    task = task_manager.get_task_summary(task_id)
    if not task:
        return
    queue_id = task.get("queue_id")
    if not queue_id:
        return

    with _lock:
        queue = _queues.get(queue_id)
        if not queue:
            return
        queue["status"] = "running"
        queue["current_task_id"] = task_id
        if not queue.get("started_at"):
            queue["started_at"] = _now_iso()
        if task_id not in queue.get("started_task_ids", []):
            queue.setdefault("started_task_ids", []).append(task_id)
        _persist_queue(queue)


def enqueue_resumed_task(task_id: str) -> None:
    """将恢复的任务放回队列排队等待，不立即启动。"""
    _ensure_loaded()

    from api.services import task_manager

    task = task_manager.get_task_summary(task_id)
    if not task:
        return
    queue_id = task.get("queue_id")
    if not queue_id:
        return

    with _lock:
        queue = _queues.get(queue_id)
        if not queue:
            return
        task_ids = queue.get("task_ids", [])
        if task_id not in task_ids:
            return
        index = task_ids.index(task_id)
        total = len(task_ids)
        _persist_queue(queue)

    phase = f"任务已恢复，队列等待中（{index + 1}/{total}），等待前序任务完成"
    task_manager.update_task_phase(task_id, phase)
    logger.info("任务 %s 已恢复并排队等待（位置 %d/%d）", task_id, index + 1, total)


def mark_task_paused(task_id: str) -> None:
    _ensure_loaded()

    from api.services import task_manager

    task = task_manager.get_task_summary(task_id)
    if not task:
        return
    queue_id = task.get("queue_id")
    if not queue_id:
        return

    with _lock:
        queue = _queues.get(queue_id)
        if not queue or queue.get("current_task_id") != task_id:
            return
        queue["status"] = "paused"
        _persist_queue(queue)


def resume_queue(queue_id: str) -> dict:
    """
    恢复整个队列：将队列中所有暂停/停止/失败的任务一次性恢复并提交给调度器。
    调度器根据并发上限自行控制执行顺序。

    Returns:
        {"resumed": [...task_ids], "skipped": [...task_ids], "already_running": [...task_ids]}
    """
    _ensure_loaded()

    from api.services import crawl_service, task_manager

    with _lock:
        queue = _queues.get(queue_id)
        if not queue:
            raise ValueError(f"任务队列不存在: {queue_id}")
        task_ids = list(queue.get("task_ids", []))

    resumed_ids: list[str] = []
    skipped_ids: list[str] = []
    already_running_ids: list[str] = []

    for task_id in task_ids:
        task = task_manager.get_task_summary(task_id)
        if not task:
            skipped_ids.append(task_id)
            continue

        status = task.get("status", "")

        if status in ("running", "pending"):
            # 检查线程是否真的活着——后端重启后内存状态可能残留 running/pending
            if task_manager.is_thread_alive(task_id):
                already_running_ids.append(task_id)
                continue
            # 线程已死但状态残留：重置后重新入队
            logger.info("resume_queue: task=%s 状态=%s 但线程已死，重新入队", task_id[:8], status)
            task_manager.update_task_status(task_id, "stopped")
            task_manager.resume_finished_task(task_id)
            crawl_service.start_crawler_thread(task_id, task, force_new_browser=True)
            resumed_ids.append(task_id)
            continue

        if status in ("paused",):
            # 暂停中的任务：如果线程活着就唤醒，否则重置状态后重新提交调度器
            if task_manager.is_thread_alive(task_id):
                task_manager.resume_task(task_id)
            else:
                # 线程不活：先标记为 stopped，再走 resume_finished_task → 入队
                task_manager.update_task_status(task_id, "stopped")
                task_manager.resume_finished_task(task_id)
                crawl_service.start_crawler_thread(task_id, task, force_new_browser=True)
            resumed_ids.append(task_id)

        elif status in ("stopped", "failed"):
            # 已结束但未完成的任务：从断点恢复
            success = task_manager.resume_finished_task(task_id)
            if success:
                crawl_service.start_crawler_thread(task_id, task, force_new_browser=True)
                resumed_ids.append(task_id)
            else:
                skipped_ids.append(task_id)
        elif status == "done":
            # 已完成的任务不自动重启
            skipped_ids.append(task_id)
        else:
            skipped_ids.append(task_id)

    # 更新队列状态
    with _lock:
        queue = _queues.get(queue_id)
        if queue:
            if resumed_ids or already_running_ids:
                queue["status"] = "running"
                queue["current_task_id"] = (already_running_ids or resumed_ids)[0]
                queue["finished_at"] = None
                if not queue.get("started_at"):
                    queue["started_at"] = _now_iso()
                for tid in resumed_ids:
                    if tid not in queue.get("started_task_ids", []):
                        queue.setdefault("started_task_ids", []).append(tid)
            _persist_queue(queue)

    logger.info(
        "队列 %s 恢复完成: resumed=%d, already_running=%d, skipped=%d",
        queue_id, len(resumed_ids), len(already_running_ids), len(skipped_ids),
    )
    return {
        "resumed": resumed_ids,
        "skipped": skipped_ids,
        "already_running": already_running_ids,
    }


def notify_task_terminal(task_id: str, status: str) -> None:
    """
    任务终态通知。
    更新队列状态，并在并发模式下自动调度同队列中下一个等待的任务。
    """
    _ensure_loaded()

    from api.services import task_manager, crawl_service
    from config import settings

    with _lock:
        queue_id = _task_to_queue.get(task_id)
        queue = _queues.get(queue_id) if queue_id else None
        if not queue:
            return

        task_ids = queue.get("task_ids", [])
        if task_id not in task_ids:
            return

        # 检查是否还有未完成的任务，同时收集需要恢复的任务
        first_active_id = None
        all_done = True
        stalled_ids: list[str] = []  # 状态残留但线程已死的任务
        for tid in task_ids:
            t = task_manager.get_task_summary(tid)
            if not t:
                continue
            t_status = t.get("status", "")
            if t_status not in _TERMINAL_STATUSES:
                all_done = False
                if first_active_id is None:
                    first_active_id = tid
                # 检测状态残留：running/pending 但线程已死
                if t_status in ("running", "pending") and not task_manager.is_thread_alive(tid):
                    stalled_ids.append(tid)

        if all_done:
            queue["status"] = "completed"
            queue["current_task_id"] = None
            queue["finished_at"] = _now_iso()
        else:
            queue["status"] = "running"
            queue["current_task_id"] = first_active_id
            queue["finished_at"] = None
        _persist_queue(queue)

    # 并发模式下：通过调度器恢复状态残留的任务（受并发限制保护，不直接启动线程）
    max_concurrent = int(settings.crawler_max_concurrent_tasks)
    if max_concurrent > 1 and stalled_ids:
        from api.services.task_scheduler import scheduler
        for tid in stalled_ids:
            t = task_manager.get_task_summary(tid)
            if not t:
                continue
            logger.info("notify_task_terminal: 恢复残留任务 %s（状态=%s 但线程已死）", tid[:8], t.get("status"))
            task_manager.update_task_status(tid, "stopped")
            task_manager.resume_finished_task(tid)
            platform = t.get("platform", "x")
            scheduler.enqueue(tid, t, platform=platform)
