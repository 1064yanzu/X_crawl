"""
任务管理器（升级版 v2）
新增：resumed 字段支持、实时进度字段 current_page
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from api.schemas.task import TaskStatus

logger = logging.getLogger(__name__)

_tasks: dict[str, dict] = {}


def create_task(keyword: str, max_count: int, product: str, task_id: Optional[str] = None) -> str:
    """创建（或复用）任务，返回 task_id"""
    tid = task_id or str(uuid.uuid4())
    # 若已存在（断点续爬复用），保留历史信息但重置状态
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
        "resumed": False,
        "tweets": existing.get("tweets", []),
    }
    logger.info(f"任务已创建/重置: task_id={tid}, keyword='{keyword}'")
    return tid


def get_task(task_id: str) -> Optional[dict]:
    return _tasks.get(task_id)


def list_tasks() -> list[dict]:
    tasks = list(_tasks.values())
    tasks.sort(key=lambda t: t["created_at"], reverse=True)
    return tasks


def update_task_status(task_id: str, status: TaskStatus) -> None:
    if task_id in _tasks:
        _tasks[task_id]["status"] = status
        if status in ("done", "failed"):
            _tasks[task_id]["finished_at"] = _now_iso()


def update_task_progress(task_id: str, current_page: int, tweets_so_far: list[dict]) -> None:
    """爬虫每爬完一页后调用，实时更新进度（不改变 status）"""
    if task_id in _tasks:
        _tasks[task_id].update({
            "current_page": current_page,
            "result_count": len(tweets_so_far),
            "tweets": tweets_so_far,
        })


def update_task_result(task_id: str, tweets: list[dict], resumed: bool = False) -> None:
    if task_id in _tasks:
        _tasks[task_id].update({
            "tweets": tweets,
            "result_count": len(tweets),
            "status": "done",
            "finished_at": _now_iso(),
            "resumed": resumed,
        })


def update_task_error(task_id: str, error: str) -> None:
    if task_id in _tasks:
        _tasks[task_id].update({
            "status": "failed",
            "error": error,
            "finished_at": _now_iso(),
        })


def delete_task(task_id: str) -> bool:
    if task_id in _tasks:
        del _tasks[task_id]
        return True
    return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
