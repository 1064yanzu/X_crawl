"""
任务管理器（v5）
新增：SQLite 持久化——服务重启后历史记录不丢失
架构：内存缓存（_tasks dict）+ 磁盘持久化（task_db）双层
"""
import uuid
import threading
import logging
from datetime import datetime, timezone
from typing import Optional
from api.schemas.task import TaskStatus

logger = logging.getLogger(__name__)

_tasks: dict[str, dict] = {}

# ── 任务控制信号 ──────────────────────────────────────────────────────
_task_signals: dict[str, str] = {}
_signal_lock = threading.Lock()

# ── 爬虫线程注册表 ─────────────────────────────────────────────────────
_task_threads: dict[str, threading.Thread] = {}

# ── 延迟初始化标志 ─────────────────────────────────────────────────────
_db_initialized = False
_db_lock = threading.Lock()


def _get_db():
    """延迟导入 task_db，避免循环依赖"""
    from api.services import task_db
    return task_db


def _ensure_db():
    """确保数据库已初始化（只初始化一次）"""
    global _db_initialized
    if _db_initialized:
        return
    with _db_lock:
        if _db_initialized:
            return
        from config import settings
        db = _get_db()
        db.init_db(settings.tasks_db_path)
        # 从数据库加载历史任务到内存
        history = db.load_all_tasks()
        for task in history:
            tid = task["task_id"]
            _tasks[tid] = task
            # 历史任务中如果状态为 running/pending/paused，重置为 stopped
            # （未正常结束的任务，重启后标记为 stopped 避免误导用户）
            if _tasks[tid]["status"] in ("running", "pending", "paused"):
                _tasks[tid]["status"] = "stopped"
                _tasks[tid]["finished_at"] = _now_iso()
                db.save_task(_tasks[tid])
        _db_initialized = True


# 在模块加载时立即初始化
try:
    _ensure_db()
except Exception as e:
    logger.warning(f"任务数据库初始化失败（将在首次操作时重试）: {e}")


def _persist(task_id: str) -> None:
    """将内存中的任务数据持久化到数据库"""
    task = _tasks.get(task_id)
    if task:
        try:
            _get_db().save_task(task)
        except Exception as e:
            logger.error(f"持久化任务失败 task_id={task_id}: {e}")


# ── 任务控制信号 ──────────────────────────────────────────────────────

def send_signal(task_id: str, signal: str) -> None:
    """发送控制信号给指定任务（run / pause / stop）"""
    with _signal_lock:
        _task_signals[task_id] = signal
    logger.info(f"信号已发送: task_id={task_id}, signal={signal}")


def get_signal(task_id: str | None) -> str:
    """获取当前任务信号，未设置则返回 'run'"""
    if not task_id:
        return "run"
    with _signal_lock:
        return _task_signals.get(task_id, "run")


def clear_signal(task_id: str) -> None:
    """清除任务信号（任务结束后调用）"""
    with _signal_lock:
        _task_signals.pop(task_id, None)


def register_thread(task_id: str, thread: threading.Thread) -> None:
    """注册任务对应的爬虫线程"""
    _task_threads[task_id] = thread


def is_thread_alive(task_id: str) -> bool:
    """检查任务的爬虫线程是否存活"""
    thread = _task_threads.get(task_id)
    return thread is not None and thread.is_alive()


def clear_thread(task_id: str) -> None:
    """清除线程注册（任务结束后调用）"""
    _task_threads.pop(task_id, None)


def pause_task(task_id: str) -> bool:
    """暂停任务，返回是否成功"""
    _ensure_db()
    task = _tasks.get(task_id)
    if not task or task["status"] not in ("running",):
        return False
    send_signal(task_id, "pause")
    _tasks[task_id]["status"] = "paused"
    logger.info(f"任务已暂停: task_id={task_id}")
    _persist(task_id)
    return True


def resume_task(task_id: str) -> bool:
    """继续已暂停的任务，返回是否成功"""
    _ensure_db()
    task = _tasks.get(task_id)
    if not task:
        return False
    current_signal = get_signal(task_id)
    if task["status"] not in ("paused",) and current_signal != "pause":
        return False
    send_signal(task_id, "run")
    _tasks[task_id]["status"] = "running"
    logger.info(f"任务已恢复: task_id={task_id}")
    _persist(task_id)
    return True


def stop_task(task_id: str) -> bool:
    """主动终止任务（区别于失败），返回是否成功"""
    _ensure_db()
    task = _tasks.get(task_id)
    if not task or task["status"] not in ("running", "paused", "pending"):
        return False
    send_signal(task_id, "stop")
    logger.info(f"终止信号已发送: task_id={task_id}")
    return True


# ── 任务 CRUD ─────────────────────────────────────────────────────────

def create_task(
    keyword: str,
    max_count: int,
    product: str,
    task_id: Optional[str] = None,
    fetch_replies: bool = False,
    max_replies_per_tweet: int = 20,
    crawl_strategy: str = "bfs",
) -> str:
    """创建（或复用）任务，返回 task_id"""
    _ensure_db()
    tid = task_id or str(uuid.uuid4())
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
        # 回复相关
        "fetch_replies": fetch_replies,
        "max_replies_per_tweet": max_replies_per_tweet,
        "crawl_strategy": crawl_strategy,
        "replies_fetched": existing.get("replies_fetched", 0),
        # 数据（完整 + 预览）
        "tweets": existing.get("tweets", []),
        "preview_tweets": existing.get("preview_tweets", []),
        # 爬虫实时阶段状态
        "crawl_phase": "",
    }
    send_signal(tid, "run")
    _persist(tid)
    logger.info(
        f"任务已创建/重置: task_id={tid}, keyword='{keyword}', "
        f"strategy={crawl_strategy}, fetch_replies={fetch_replies}"
    )
    return tid


def get_task(task_id: str) -> Optional[dict]:
    _ensure_db()
    return _tasks.get(task_id)


def list_tasks() -> list[dict]:
    _ensure_db()
    tasks = list(_tasks.values())
    tasks.sort(key=lambda t: t["created_at"], reverse=True)
    return tasks


def update_task_status(task_id: str, status: TaskStatus) -> None:
    if task_id in _tasks:
        _tasks[task_id]["status"] = status
        if status in ("done", "failed", "stopped"):
            _tasks[task_id]["finished_at"] = _now_iso()
            clear_signal(task_id)
        _persist(task_id)


def update_task_phase(task_id: str, phase: str) -> None:
    """实时更新爬虫当前阶段（极高频，不持久化到数据库）"""
    if task_id in _tasks:
        _tasks[task_id]["crawl_phase"] = phase


def update_task_progress(task_id: str, current_page: int, tweets_so_far: list[dict]) -> None:
    """爬虫每爬完一页后调用，实时更新进度（同步持久化）"""
    from config import settings
    if task_id in _tasks:
        replies_fetched = sum(len(t.get("replies", [])) for t in tweets_so_far)
        preview_count = settings.crawler_preview_count
        preview = tweets_so_far[-preview_count:] if len(tweets_so_far) > preview_count else tweets_so_far
        _tasks[task_id].update({
            "current_page": current_page,
            "result_count": len(tweets_so_far),
            "replies_fetched": replies_fetched,
            "tweets": tweets_so_far,
            "preview_tweets": preview,
        })
        _persist(task_id)


def update_task_replies_progress(task_id: str, tweet_id: str, reply_count: int) -> None:
    """每条推文回复抓取完成后调用，累加 replies_fetched（DFS 模式实时更新）"""
    if task_id in _tasks:
        _tasks[task_id]["replies_fetched"] = (
            _tasks[task_id].get("replies_fetched", 0) + reply_count
        )
        _persist(task_id)


def update_task_result(task_id: str, tweets: list[dict], resumed: bool = False, replies_fetched: int = 0) -> None:
    from config import settings
    if task_id in _tasks:
        preview_count = settings.crawler_preview_count
        preview = tweets[-preview_count:] if len(tweets) > preview_count else tweets
        _tasks[task_id].update({
            "tweets": tweets,
            "preview_tweets": preview,
            "result_count": len(tweets),
            "status": "done",
            "finished_at": _now_iso(),
            "resumed": resumed,
            "replies_fetched": replies_fetched,
        })
        clear_signal(task_id)
        _persist(task_id)


def update_task_stopped(task_id: str, tweets_so_far: list[dict]) -> None:
    """主动终止任务时调用，保存已抓取数据"""
    from config import settings
    if task_id in _tasks:
        preview_count = settings.crawler_preview_count
        preview = tweets_so_far[-preview_count:] if len(tweets_so_far) > preview_count else tweets_so_far
        _tasks[task_id].update({
            "tweets": tweets_so_far,
            "preview_tweets": preview,
            "result_count": len(tweets_so_far),
            "status": "stopped",
            "finished_at": _now_iso(),
        })
        clear_signal(task_id)
        _persist(task_id)


def update_task_error(task_id: str, error: str) -> None:
    if task_id in _tasks:
        _tasks[task_id].update({
            "status": "failed",
            "error": error,
            "finished_at": _now_iso(),
        })
        clear_signal(task_id)
        _persist(task_id)


def delete_task(task_id: str) -> bool:
    if task_id in _tasks:
        del _tasks[task_id]
        clear_signal(task_id)
        try:
            _get_db().delete_task(task_id)
        except Exception as e:
            logger.error(f"从数据库删除任务失败 task_id={task_id}: {e}")
        return True
    return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
