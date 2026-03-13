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
            queue_id=queue_id,
            queue_name=queue_name,
            queue_order=index,
            queue_total=total,
        )
        phase = (
            "队列首个任务已创建，正在进入调度队列..."
            if index == 1
            else f"任务队列等待中（{index}/{total}），等待前序任务完成"
        )
        task_manager.update_task_phase(task_id, phase)
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
        "started_task_ids": [task_ids[0]] if task_ids else [],
    }

    with _lock:
        _queues[queue_id] = queue
        for task_id in task_ids:
            _task_to_queue[task_id] = queue_id
        _persist_queue(queue)

    first_task = task_manager.get_task_summary(task_ids[0]) if task_ids else None
    if first_task:
        crawl_service.start_crawler_thread(task_ids[0], first_task, resume=False)
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


def can_resume_task(task_id: str) -> tuple[bool, Optional[str]]:
    _ensure_loaded()

    from api.services import task_manager

    task = task_manager.get_task_summary(task_id)
    if not task:
        return False, "任务不存在"

    queue_id = task.get("queue_id")
    if not queue_id:
        return True, None

    with _lock:
        queue = copy.deepcopy(_queues.get(queue_id))
    if not queue:
        return True, None

    task_ids = queue.get("task_ids", [])
    if task_id not in task_ids:
        return True, None

    current_task_id = queue.get("current_task_id")
    if current_task_id and current_task_id != task_id:
        current_task = task_manager.get_task_summary(current_task_id)
        if current_task and current_task.get("status") not in _TERMINAL_STATUSES:
            return False, "当前队列还有前序任务未完成，不能插队继续"

    index = task_ids.index(task_id)
    for prev_task_id in task_ids[:index]:
        prev_task = task_manager.get_task_summary(prev_task_id)
        if prev_task and prev_task.get("status") not in _TERMINAL_STATUSES:
            return False, "必须等待前序任务结束后才能继续当前队列项"

    return True, None


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


def notify_task_terminal(task_id: str, status: str) -> None:
    _ensure_loaded()

    from api.services import crawl_service, task_manager

    with _lock:
        queue_id = _task_to_queue.get(task_id)
        queue = _queues.get(queue_id) if queue_id else None
        if not queue:
            return

        task_ids = queue.get("task_ids", [])
        if task_id not in task_ids:
            return

        index = task_ids.index(task_id)
        next_task_id = task_ids[index + 1] if index + 1 < len(task_ids) else None
        if next_task_id:
            queue["status"] = "running"
            queue["current_task_id"] = next_task_id
            queue["finished_at"] = None
            if next_task_id not in queue.get("started_task_ids", []):
                queue.setdefault("started_task_ids", []).append(next_task_id)
        else:
            queue["status"] = "completed"
            queue["current_task_id"] = None
            queue["finished_at"] = _now_iso()
        _persist_queue(queue)

    if not next_task_id:
        return

    phase = f"前序任务已结束（{status}），当前开始执行队列项 {index + 2}/{len(task_ids)}"
    task_manager.restore_waiting_task(next_task_id, phase)
    next_task = task_manager.get_task_summary(next_task_id)
    if next_task:
        crawl_service.start_crawler_thread(next_task_id, next_task, resume=False)
