"""
任务管理器（线程安全 + 节流持久化 + 结果懒加载 + LRU 缓存）。
"""
from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

from api.schemas.task import RiskState, TaskStatus
from json_utils import normalize_json_value

logger = logging.getLogger(__name__)

_tasks: dict[str, dict] = {}
_task_results: OrderedDict[str, list[dict]] = OrderedDict()  # 改为 OrderedDict 支持 LRU
_loaded_task_results: set[str] = set()
_tasks_lock = threading.RLock()

# LRU 缓存计量（容量与字节双门限，运行中/暂停任务不淘汰）
_DEFAULT_RESULT_CACHE_MAX_SIZE = 16
_RESULT_BYTES_PER_TWEET = 32 * 1024  # 每条推文（含回复树）粗估占用，仅用于上界估算
_lru_evictions = 0  # 累计淘汰次数（含字节门限触发），供 memory-stats 观测


def _result_cache_max_size() -> int:
    """LRU 条目上限（读 settings，默认 16，硬上限 256 防误配）。"""
    from config import settings

    raw = getattr(settings, "crawler_result_cache_max_size", _DEFAULT_RESULT_CACHE_MAX_SIZE)
    try:
        return max(1, min(256, int(raw)))
    except (TypeError, ValueError):
        return _DEFAULT_RESULT_CACHE_MAX_SIZE


def _result_cache_max_bytes() -> int:
    """LRU 字节上限（读 settings，默认 512MB，下限 64MB）。"""
    from config import settings

    try:
        mb = float(getattr(settings, "crawler_result_cache_max_mb", 512.0))
    except (TypeError, ValueError):
        mb = 512.0
    return int(max(64.0, mb) * 1024 * 1024)


def _estimate_cache_bytes() -> int:
    """粗估 LRU 当前占用字节（条目推文数 × 经验系数，不做昂贵的 getsizeof）。"""
    return sum(len(v) for v in _task_results.values()) * _RESULT_BYTES_PER_TWEET


def get_memory_stats() -> dict:
    """返回任务结果 LRU 缓存的实时占用与命中/淘汰指标，供 /system/memory-stats。"""
    with _tasks_lock:
        entries = len(_task_results)
        total_tweets = sum(len(v) for v in _task_results.values())
        loaded = len(_loaded_task_results)
        evictions = _lru_evictions
    return {
        "lru_entries": entries,
        "lru_loaded_marks": loaded,
        "lru_total_tweets": total_tweets,
        "lru_max_size": _result_cache_max_size(),
        "lru_max_mb": round(_result_cache_max_bytes() / 1024 / 1024, 1),
        "lru_estimated_mb": round(total_tweets * _RESULT_BYTES_PER_TWEET / 1024 / 1024, 2),
        "lru_evictions": evictions,
    }

_task_signals: dict[str, str] = {}
_signal_lock = threading.Lock()

# Resume Event 字典：任务 ID -> Event（用于 pause/resume 即时唤醒）
_resume_events: dict[str, threading.Event] = {}
_resume_events_lock = threading.Lock()

_task_threads: dict[str, threading.Thread] = {}
_threads_lock = threading.RLock()

_persist_mark: dict[str, float] = {}
_persist_mark_lock = threading.Lock()
_PERSIST_MIN_INTERVAL_SEC = 0.4

# reply snapshot 增量缓存：避免每条评论都全表走查
_reply_summary_cache: dict[str, dict] = {}  # task_id -> {replies_fetched, coverage}
_reply_summary_cache_lock = threading.Lock()
_reply_persist_counter: dict[str, int] = {}  # task_id -> counter（每 30 条或 30 秒触发完整落盘）
_reply_last_full_persist: dict[str, float] = {}  # task_id -> last_time

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


def _default_comment_backfill_progress() -> dict:
    return {
        "total_posts": 0,
        "eligible_posts": 0,
        "processed_posts": 0,
        "skipped_posts": 0,
        "succeeded_posts": 0,
        "failed_posts": 0,
        "total_expected_replies": 0,
    }


def _default_task_state(*, task_id: str, keyword: str, product: str) -> dict:
    return {
        "task_id": task_id,
        "status": "pending",
        "keyword": keyword,
        "product": product,
        "result_count": 0,
        "current_page": 0,
        "created_at": _now_iso(),
        "finished_at": None,
        "error": None,
        "risk_state": "none",
        "quality_state": "complete",
        "runtime_metrics": {},
        "live_metrics": {},
        "time_coverage": {},
        "latest_action": None,
        "queue_position": None,
        "last_event_at": _now_iso(),
        "resumed": False,
        "segment_progress": _default_segment_progress(),
        "fetch_replies": False,
        "crawl_strategy": "dfs",
        "max_replies_per_tweet": 20,
        "reply_depth": 2,
        "replies_fetched": 0,
        "task_kind": "search",
        "source_file_name": None,
        "source_task_id": None,
        "is_recrawl": False,
        "exclude_count": 0,
        "exclude_tweet_ids": [],
        "queue_id": None,
        "queue_name": None,
        "queue_order": None,
        "queue_total": None,
        "comment_backfill_progress": _default_comment_backfill_progress(),
        "preview_tweets": [],
        "crawl_phase": "",
        "platform": "x",
        "start_date": None,
        "end_date": None,
        "time_split_mode": "inherit",
        "time_split_window_days": None,
        "time_split_max_segments": None,
        "debug_screenshot": None,
        "assigned_account_id": None,
        "account_alias": None,
        "youtube": None,
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


def _parse_iso(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _span_hours(start: Optional[datetime], end: Optional[datetime]) -> float:
    if not start or not end:
        return 0.0
    seconds = (end - start).total_seconds()
    if seconds <= 0:
        return 0.0
    return round(seconds / 3600.0, 2)


def _safe_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _merge_coverage(existing: Optional[dict], delta: Optional[dict]) -> dict:
    existing = dict(existing or {})
    delta = dict(delta or {})
    if not existing:
        return delta
    if not delta:
        return existing

    def _merge_window(prefix: str) -> None:
        start = min(
            [dt for dt in (_parse_iso(existing.get(f"{prefix}_start_at")), _parse_iso(delta.get(f"{prefix}_start_at"))) if dt],
            default=None,
        )
        end = max(
            [dt for dt in (_parse_iso(existing.get(f"{prefix}_end_at")), _parse_iso(delta.get(f"{prefix}_end_at"))) if dt],
            default=None,
        )
        existing[f"{prefix}_start_at"] = _to_iso(start)
        existing[f"{prefix}_end_at"] = _to_iso(end)
        existing[f"{prefix}_span_hours"] = _span_hours(start, end)
        existing[f"{prefix}_ts_count"] = _safe_int(existing.get(f"{prefix}_ts_count", 0)) + _safe_int(
            delta.get(f"{prefix}_ts_count", 0)
        )

    _merge_window("tweet")
    _merge_window("reply")
    _merge_window("combined")
    return existing


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

    enriched = dict(task)
    enriched["runtime_metrics"] = runtime_metrics
    enriched["live_metrics"] = live_metrics
    enriched["latest_action"] = telemetry.get_latest_action(task_id)
    enriched["queue_position"] = queue_position
    return enriched


def _set_task_result_locked(task_id: str, tweets: list[dict]) -> None:
    """设置任务结果到缓存，触发 LRU 淘汰逻辑"""
    # 如果已存在，移到最新位置
    if task_id in _task_results:
        _task_results.move_to_end(task_id)
    else:
        _task_results[task_id] = tweets

    _loaded_task_results.add(task_id)

    # LRU 淘汰：条目数 OR 估算字节超限时移除最旧的（但不淘汰运行中/暂停任务）
    global _lru_evictions
    max_size = _result_cache_max_size()
    max_bytes = _result_cache_max_bytes()
    guard = 0
    limit = len(_task_results) + 4  # 护栏：全是活跃任务时避免空转死循环
    while len(_task_results) > 1 and (
        len(_task_results) > max_size or _estimate_cache_bytes() > max_bytes
    ):
        guard += 1
        if guard > limit:
            break
        oldest_id, oldest_val = _task_results.popitem(last=False)
        # 如果最旧的任务还在运行/暂停，不淘汰它
        if oldest_id in _tasks and _tasks[oldest_id].get("status") in ("running", "paused"):
            _task_results[oldest_id] = oldest_val
            _task_results.move_to_end(oldest_id)
            continue
        _loaded_task_results.discard(oldest_id)
        _lru_evictions += 1
        logger.debug(f"LRU 淘汰任务结果: {oldest_id}")


def _get_task_result_snapshot(task_id: str, *, load: bool = False) -> list[dict]:
    """获取任务结果的深拷贝快照"""
    with _tasks_lock:
        if task_id in _loaded_task_results:
            # LRU 命中，移到最新位置
            if task_id in _task_results:
                _task_results.move_to_end(task_id)
            return copy.deepcopy(_task_results.get(task_id, []))

    if not load:
        return []

    tweets = _get_db().load_task_result(task_id)
    with _tasks_lock:
        if task_id not in _loaded_task_results:
            _set_task_result_locked(task_id, tweets)
        return copy.deepcopy(_task_results.get(task_id, []))


def _get_task_result_ref(task_id: str, *, load: bool = False) -> list[dict]:
    """获取推文列表的零拷贝引用（用于评论补采等内部写入场景）。

    调用方直接操作返回的列表和对象，避免对 8000+ 条含嵌套回复树的推文
    做 copy.deepcopy（该操作可能耗时数分钟）。
    """
    with _tasks_lock:
        if task_id in _loaded_task_results:
            # LRU 命中，移到最新位置
            if task_id in _task_results:
                _task_results.move_to_end(task_id)
            return _task_results.get(task_id, [])

    if not load:
        return []

    tweets = _get_db().load_task_result(task_id)
    with _tasks_lock:
        if task_id not in _loaded_task_results:
            _set_task_result_locked(task_id, tweets)
        return _task_results.get(task_id, [])


# 摘要字段白名单（避免 deepcopy 大对象）
_SUMMARY_KEYS = {
    "task_id", "status", "keyword", "product", "max_count", "result_count",
    "current_page", "created_at", "finished_at", "error", "risk_state",
    "quality_state", "last_event_at", "resumed", "fetch_replies",
    "max_replies_per_tweet", "reply_depth", "crawl_strategy", "replies_fetched",
    "crawl_phase", "task_kind", "source_file_name", "source_task_id",
    "source_task_ids", "is_recrawl", "exclude_count", "exclude_tweet_ids",
    "queue_id", "queue_name", "queue_order", "queue_total",
    "debug_screenshot", "assigned_account_id", "account_alias",
    "platform", "start_date", "end_date", "time_split_mode",
    "time_split_window_days", "time_split_max_segments", "concurrency",
    "youtube",
}


def _get_task_summary_snapshot(task_id: str) -> Optional[dict]:
    """
    获取任务摘要快照（优化版：白名单浅拷贝，避免 deepcopy 大对象）

    已知大字段（runtime_metrics, segment_progress, time_coverage,
    comment_backfill_progress, preview_tweets）单独处理，不走 deepcopy。
    """
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return None

        # 白名单浅拷贝
        snapshot = {k: task[k] for k in _SUMMARY_KEYS if k in task}

        # 大字段单独处理（浅拷贝字典/列表）
        if "runtime_metrics" in task:
            snapshot["runtime_metrics"] = dict(task["runtime_metrics"])
        if "segment_progress" in task:
            snapshot["segment_progress"] = dict(task["segment_progress"])
        if "time_coverage" in task:
            snapshot["time_coverage"] = dict(task["time_coverage"])
        if "comment_backfill_progress" in task:
            snapshot["comment_backfill_progress"] = dict(task["comment_backfill_progress"])
        if "preview_tweets" in task:
            snapshot["preview_tweets"] = list(task["preview_tweets"])

        return snapshot


def _build_task_view(task_id: str, *, include_tweets: bool) -> Optional[dict]:
    snapshot = _get_task_summary_snapshot(task_id)
    if not snapshot:
        return None
    queue_position = _queue_positions().get(task_id) if snapshot.get("status") == "pending" else None
    view = _decorate_task_runtime(snapshot, queue_position=queue_position)
    view["tweets"] = _get_task_result_snapshot(task_id, load=True) if include_tweets else []
    return view


def _ensure_db() -> None:
    global _db_initialized
    if _db_initialized:
        return

    with _db_lock:
        if _db_initialized:
            return

        from config import settings, resolve_data_path

        db = _get_db()
        db_path = str(resolve_data_path(settings.tasks_db_path))
        db.init_db(db_path)

        # 初始化采集量分桶数据库（与主库共用同一文件）
        try:
            from api.services.crawl_volume_db import init_volume_db
            init_volume_db(db_path)
        except Exception as _e:
            logger.warning(f"采集量分桶数据库初始化失败（忽略）: {_e}")

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
                task.setdefault("time_split_mode", "inherit")
                task.setdefault("time_split_window_days", None)
                task.setdefault("time_split_max_segments", None)
                task.setdefault("preview_tweets", [])
                task.setdefault("replies_fetched", 0)
                task.setdefault("reply_depth", 2)
                task.setdefault("task_kind", "search")
                task.setdefault("source_file_name", None)
                task.setdefault("source_task_id", None)
                task.setdefault("source_task_ids", [])
                task.setdefault("is_recrawl", False)
                task.setdefault("exclude_count", 0)
                task.setdefault("exclude_tweet_ids", [])
                task.setdefault("queue_id", None)
                task.setdefault("queue_name", None)
                task.setdefault("queue_order", None)
                task.setdefault("queue_total", None)
                task.setdefault("comment_backfill_progress", _default_comment_backfill_progress())
                task.setdefault("debug_screenshot", None)

                if task["status"] in ("running", "pending", "paused"):
                    task["status"] = "stopped"
                    task["quality_state"] = "interrupted"
                    task["finished_at"] = _now_iso()
                    _touch(task)
                    db.save_task_summary(task)
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
            snapshot["tweets"] = _get_task_result_snapshot(task_id, load=True)
            _get_db().save_task(snapshot)
        else:
            _get_db().save_task_summary(snapshot)
    except Exception as e:
        logger.error(f"持久化任务失败 task_id={task_id}: {e}")


def _persist_force(task_id: str, *, full: bool = True) -> None:
    _persist(task_id, force=True, full=full)


def _mark_persist(task_id: str) -> None:
    """
    标记任务摘要需要持久化。

    用于只修改任务元信息的轻量更新场景，保留原有节流语义，
    避免账号绑定/释放等高频操作频繁触发全量落库。
    """
    _persist(task_id, full=False)


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
    # 同时清理 resume event
    with _resume_events_lock:
        _resume_events.pop(task_id, None)


def get_or_create_resume_event(task_id: str) -> threading.Event:
    """获取或创建任务的 resume Event（用于 pause/resume 即时唤醒）"""
    with _resume_events_lock:
        if task_id not in _resume_events:
            _resume_events[task_id] = threading.Event()
        return _resume_events[task_id]


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
        # 保留暂停前的阶段描述，供恢复时还原
        task["_paused_phase"] = task.get("crawl_phase", "")
        task["crawl_phase"] = "任务已暂停，等待继续信号"
        _touch(task)
    send_signal(task_id, "pause")
    telemetry.record_event(task_id, "task_paused", status="paused", phase="任务已暂停，等待继续信号")
    _persist_force(task_id, full=True)
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
        # 恢复暂停前的阶段描述
        saved_phase = task.pop("_paused_phase", None)
        if saved_phase:
            task["crawl_phase"] = saved_phase
        else:
            task["crawl_phase"] = "任务已恢复运行"
        _touch(task)
    send_signal(task_id, "run")

    # 触发 resume Event，即时唤醒等待中的爬虫线程
    with _resume_events_lock:
        if task_id in _resume_events:
            _resume_events[task_id].set()

    telemetry.record_event(task_id, "task_resumed", status="running", phase=task.get("crawl_phase", "任务已恢复运行"))
    _persist_force(task_id, full=False)
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
    _persist_force(task_id, full=False)
    return True


def stop_task(task_id: str) -> bool:
    _ensure_db()
    from crawler import telemetry

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task or task["status"] not in ("running", "paused", "pending"):
            return False
        status = task.get("status")
    send_signal(task_id, "stop")
    telemetry.record_event(task_id, "task_stop_requested", status=status, phase="收到终止信号，等待安全退出")
    return True


def count_active_tasks() -> int:
    _ensure_db()
    with _tasks_lock:
        return sum(1 for task in _tasks.values() if task.get("status") in ("pending", "running"))


def create_task(
    keyword: str,
    legacy_limit: int = 0,
    product: str = "Top",
    task_id: Optional[str] = None,
    fetch_replies: bool = False,
    max_replies_per_tweet: int = 20,
    reply_depth: int = 2,
    crawl_strategy: str = "bfs",
    platform: str = "x",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    time_split_mode: str = "inherit",
    time_split_window_days: Optional[int] = None,
    time_split_max_segments: Optional[int] = None,
    task_kind: str = "search",
    source_file_name: Optional[str] = None,
    source_task_id: Optional[str] = None,
    is_recrawl: bool = False,
    queue_id: Optional[str] = None,
    queue_name: Optional[str] = None,
    queue_order: Optional[int] = None,
    queue_total: Optional[int] = None,
    comment_backfill_progress: Optional[dict] = None,
    exclude_tweet_ids: Optional[list[str]] = None,
    source_task_ids: Optional[list[str]] = None,
    concurrency: int = 1,
    youtube: Optional[dict] = None,
) -> str:
    _ensure_db()
    from crawler import telemetry

    tid = task_id or str(uuid.uuid4())

    if tid in _tasks and is_thread_alive(tid):
        logger.warning(f"任务 {tid} 的爬虫线程仍在运行，忽略重复创建")
        return tid

    with _tasks_lock:
        existing = _tasks.get(tid) or _default_task_state(
            task_id=tid,
            keyword=keyword,
            product=product,
        )
        _tasks[tid] = {
            **existing,
            "task_id": tid,
            "status": "pending",
            "keyword": keyword,
            "product": product,
            "finished_at": None,
            "error": None,
            "risk_state": "none",
            "quality_state": "complete",
            "last_event_at": _now_iso(),
            "resumed": False,
            "fetch_replies": fetch_replies,
            "max_replies_per_tweet": max_replies_per_tweet,
            "reply_depth": reply_depth,
            "crawl_strategy": crawl_strategy,
            "task_kind": task_kind,
            "source_file_name": source_file_name,
            "source_task_id": source_task_id,
            "source_task_ids": source_task_ids or [],
            "is_recrawl": is_recrawl,
            "queue_id": queue_id,
            "queue_name": queue_name,
            "queue_order": queue_order,
            "queue_total": queue_total,
            "comment_backfill_progress": {
                **_default_comment_backfill_progress(),
                **(comment_backfill_progress or {}),
            },
            "platform": platform,
            "start_date": start_date,
            "end_date": end_date,
            "time_split_mode": time_split_mode or "inherit",
            "time_split_window_days": time_split_window_days,
            "time_split_max_segments": time_split_max_segments,
            "crawl_phase": "已加入调度队列，等待执行...",
            "exclude_tweet_ids": exclude_tweet_ids or [],
            "exclude_count": len(exclude_tweet_ids) if exclude_tweet_ids else 0,
            "concurrency": concurrency,
            "youtube": youtube if isinstance(youtube, dict) else None,
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
            "task_kind": task_kind,
            "source_file_name": source_file_name,
            "source_task_id": source_task_id,
            "queue_id": queue_id,
            "queue_order": queue_order,
            "queue_total": queue_total,
        },
    )
    _persist_force(tid, full=False)
    logger.info(f"任务已创建/重置: task_id={tid}, strategy={crawl_strategy}, fetch_replies={fetch_replies}")
    return tid


def prepare_task_for_recrawl(
    task_id: str,
    *,
    keyword: str,
    legacy_limit: int = 0,
    product: str = "Top",
    fetch_replies: bool = False,
    max_replies_per_tweet: int = 20,
    reply_depth: int = 2,
    crawl_strategy: str = "bfs",
    platform: str = "x",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    time_split_mode: str = "inherit",
    time_split_window_days: Optional[int] = None,
    time_split_max_segments: Optional[int] = None,
    source_task_id: Optional[str] = None,
    exclude_tweet_ids: Optional[list[str]] = None,
) -> bool:
    """为复爬重置任务运行态，但保留已落库的 tweets 结果作为增量种子。"""
    _ensure_db()
    from crawler import telemetry

    seed_tweets = _get_task_result_snapshot(task_id, load=True)

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        if task["status"] not in ("done", "stopped", "failed"):
            return False

        task.update(
            {
                "status": "pending",
                "keyword": keyword,
                "product": product,
                "current_page": 0,
                "created_at": task.get("created_at") or _now_iso(),
                "finished_at": None,
                "error": None,
                "risk_state": "none",
                "quality_state": "complete",
                "last_event_at": _now_iso(),
                "resumed": False,
                "fetch_replies": fetch_replies,
                "max_replies_per_tweet": max_replies_per_tweet,
                "reply_depth": reply_depth,
                "crawl_strategy": crawl_strategy,
                "source_task_id": source_task_id,
                "is_recrawl": True,
                "platform": platform,
                "start_date": start_date,
                "end_date": end_date,
                "time_split_mode": time_split_mode or "inherit",
                "time_split_window_days": time_split_window_days,
                "time_split_max_segments": time_split_max_segments,
                "crawl_phase": "已加入调度队列，等待执行...",
                "exclude_tweet_ids": exclude_tweet_ids or [],
                "exclude_count": len(exclude_tweet_ids) if exclude_tweet_ids else 0,
                # 保留历史结果，作为复爬提速的种子数据
                "result_count": len(seed_tweets),
                "preview_tweets": _make_preview(seed_tweets),
            }
        )
        _touch(task)

    send_signal(task_id, "run")
    telemetry.record_event(
        task_id,
        "task_recrawl_prepared",
        status="pending",
        phase="已加入调度队列，等待执行...",
        meta={
            "keyword": keyword,
            "platform": platform,
            "exclude_count": len(exclude_tweet_ids or []),
            "seed_count": len(seed_tweets),
        },
    )
    _persist_force(task_id, full=False)
    return True


def restore_waiting_task(task_id: str, phase: str) -> bool:
    _ensure_db()
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task or is_thread_alive(task_id):
            return False
        task["status"] = "pending"
        task["finished_at"] = None
        task["error"] = None
        task["risk_state"] = "none"
        task["quality_state"] = "complete"
        task["crawl_phase"] = phase
        _touch(task)
    _persist_force(task_id, full=False)
    return True


def ensure_task_exclude_tweet_ids(task_id: str) -> list[str]:
    """为复爬任务补齐排除 ID。

    服务重启后任务摘要不会保留完整 exclude_tweet_ids，恢复任务时根据
    source_task_id（若为空则回退当前 task_id）重建。
    """
    _ensure_db()
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task or not task.get("is_recrawl"):
            return []
        existing = list(task.get("exclude_tweet_ids") or [])
        if existing:
            return existing
        source_task_id = str(task.get("source_task_id") or task_id).strip() or task_id

    source_tweets = _get_task_result_snapshot(source_task_id, load=True)
    exclude_ids = [
        str(tweet.get("id") or tweet.get("mid") or "").strip()
        for tweet in source_tweets
        if str(tweet.get("id") or tweet.get("mid") or "").strip()
    ]

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return exclude_ids
        task["exclude_tweet_ids"] = exclude_ids
        task["exclude_count"] = len(exclude_ids)
        _touch(task)
    _persist_force(task_id, full=False)
    return exclude_ids


def get_task(task_id: str) -> Optional[dict]:
    return get_task_summary(task_id)


def get_task_summary(task_id: str) -> Optional[dict]:
    _ensure_db()
    from api.services.task_watchdog import maybe_heal_stale_active_tasks

    maybe_heal_stale_active_tasks()
    return _build_task_view(task_id, include_tweets=False)


def get_task_export_payload(task_id: str) -> Optional[dict]:
    """为导出提供轻量任务视图，避免不必要的运行态装饰开销。"""
    _ensure_db()
    summary = _get_task_summary_snapshot(task_id)
    if not summary:
        return None

    return {
        "task_id": summary.get("task_id", task_id),
        "keyword": summary.get("keyword", ""),
        "platform": summary.get("platform", "x"),
        "task_kind": summary.get("task_kind", "search"),
        "fetch_replies": bool(summary.get("fetch_replies", False)),
        "replies_fetched": int(summary.get("replies_fetched", 0) or 0),
        "source_task_id": summary.get("source_task_id"),
        "source_task_ids": list(summary.get("source_task_ids") or []),
        "tweets": _get_task_result_snapshot(task_id, load=True),
    }


def get_task_export_payload_readonly(task_id: str) -> Optional[dict]:
    """导出专用只读接口——不做 deepcopy，仅在只读场景（CSV/Excel 构建）使用。
    调用方不得修改返回的 tweets 列表中的数据。"""
    _ensure_db()
    summary = _get_task_summary_snapshot(task_id)
    if not summary:
        return None

    # 确保数据已加载到内存
    with _tasks_lock:
        if task_id not in _loaded_task_results:
            tweets = _get_db().load_task_result(task_id)
            _task_results[task_id] = tweets
            _loaded_task_results.add(task_id)
        tweets_ref = _task_results.get(task_id, [])

    return {
        "task_id": summary.get("task_id", task_id),
        "keyword": summary.get("keyword", ""),
        "platform": summary.get("platform", "x"),
        "task_kind": summary.get("task_kind", "search"),
        "fetch_replies": bool(summary.get("fetch_replies", False)),
        "replies_fetched": int(summary.get("replies_fetched", 0) or 0),
        "source_task_id": summary.get("source_task_id"),
        "source_task_ids": list(summary.get("source_task_ids") or []),
        "tweets": tweets_ref,
    }


def get_export_estimate(task_ids: list[str]) -> dict:
    """返回导出预估信息：行数、推文数、评论数。"""
    _ensure_db()
    total_tweets = 0
    total_replies = 0
    task_details = []
    for task_id in task_ids:
        summary = _get_task_summary_snapshot(task_id)
        if not summary:
            continue
        tweet_count = int(summary.get("result_count", 0) or 0)
        reply_count = int(summary.get("replies_fetched", 0) or 0)
        total_tweets += tweet_count
        total_replies += reply_count
        task_details.append({
            "task_id": task_id,
            "keyword": summary.get("keyword", ""),
            "tweet_count": tweet_count,
            "reply_count": reply_count,
        })
    total_rows = total_tweets + total_replies
    # 粗略估算：每行约 500 字节 CSV / 800 字节 Excel
    estimated_csv_size = total_rows * 500
    estimated_excel_size = total_rows * 800
    return {
        "task_count": len(task_details),
        "total_tweets": total_tweets,
        "total_replies": total_replies,
        "total_rows": total_rows,
        "estimated_csv_bytes": estimated_csv_size,
        "estimated_excel_bytes": estimated_excel_size,
        "tasks": task_details,
    }


def update_task_field(task_id: str, field: str, value) -> bool:
    """更新内存中 task dict 的单个字段，并持久化到 DB。"""
    _ensure_db()
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        task[field] = value
    _persist_force(task_id, full=False)
    return True


def get_task_full(task_id: str) -> Optional[dict]:
    _ensure_db()
    from api.services.task_watchdog import maybe_heal_stale_active_tasks

    maybe_heal_stale_active_tasks()
    return _build_task_view(task_id, include_tweets=True)


def get_task_detail(
    task_id: str,
    *,
    offset: int = 0,
    limit: Optional[int] = None,
    since: Optional[str] = None,
) -> Optional[dict]:
    """只读详情视图：摘要 + 有界、浅拷贝的 tweets 窗口。

    与 get_task_full 的区别：
    - tweets 走浅拷贝（list(...) + dict(t)），不对整棵回复树 deepcopy。写入方对
      tweet / replies 均为整体替换（非原地改键/原地 append），故浅拷贝读取安全。
    - 支持 offset / limit / since 增量窗口；默认（limit=None, since=None）等价旧
      include_tweets=true 的"返回全部"语义，但开销从 deepcopy 降到浅拷贝。
    """
    _ensure_db()
    from api.services.task_watchdog import maybe_heal_stale_active_tasks

    maybe_heal_stale_active_tasks()

    summary = _get_task_summary_snapshot(task_id)
    if not summary:
        return None
    queue_position = (
        _queue_positions().get(task_id) if summary.get("status") == "pending" else None
    )
    view = _decorate_task_runtime(summary, queue_position=queue_position)

    # 取底层引用（不 deepcopy），再做有界浅拷贝
    with _tasks_lock:
        base = _task_results.get(task_id) if task_id in _loaded_task_results else None
    if base is None:
        loaded = _get_db().load_task_result(task_id)
        with _tasks_lock:
            if task_id not in _loaded_task_results:
                _set_task_result_locked(task_id, loaded)
            base = _task_results.get(task_id, loaded)

    start = max(0, int(offset or 0))
    if since:
        sid = str(since)
        idx = next(
            (
                i for i, t in enumerate(base)
                if str((t or {}).get("id") or (t or {}).get("mid") or "") == sid
            ),
            None,
        )
        if idx is not None:
            start = idx + 1
    window = base[start:] if limit is None else base[start:start + max(0, int(limit))]
    view["tweets"] = [dict(t) if isinstance(t, dict) else t for t in list(window)]
    return view


def get_task_tweets_ref(task_id: str) -> list[dict]:
    """获取推文列表的零拷贝引用（评论补采专用）。

    直接返回内存中的原始列表引用，跳过 deepcopy 和 watchdog 检查。
    对于 8000+ 条含嵌套回复树的推文，比 get_task_full 快几个数量级。
    """
    _ensure_db()
    return _get_task_result_ref(task_id, load=True)


def _shallow_copy_task(task: dict) -> dict:
    """浅拷贝任务摘要（list_tasks 只读视图专用）。

    复制已知的可变嵌套容器（dict/小 list），其余标量直接共享引用，
    避免对每个任务做整树 deepcopy。preview_tweets 由写入方整体替换而非原地
    改键，故共享其内部对象引用是安全的。
    """
    snap = dict(task)
    for k in (
        "runtime_metrics", "live_metrics", "time_coverage",
        "segment_progress", "comment_backfill_progress",
    ):
        v = task.get(k)
        if isinstance(v, dict):
            snap[k] = dict(v)
    for k in ("preview_tweets", "source_task_ids", "exclude_tweet_ids"):
        v = task.get(k)
        if isinstance(v, list):
            snap[k] = list(v)
    return snap


def list_tasks(*, include_payload: bool = False) -> list[dict]:
    _ensure_db()
    from api.services.task_watchdog import maybe_heal_stale_active_tasks

    maybe_heal_stale_active_tasks()
    with _tasks_lock:
        # 浅拷贝替代整树 deepcopy：摘要 dict 不含全量 tweets（tweets 在 _task_results），
        # 此处只需隔离嵌套容器，500+ 任务列表从 deepcopy 的数百毫秒降到亚毫秒级。
        tasks = [_shallow_copy_task(t) for t in _tasks.values()]
    queue_positions = _queue_positions()
    views = []
    for task in tasks:
        tid = task.get("task_id", "")
        view = _decorate_task_runtime(
            task,
            queue_position=queue_positions.get(tid) if task.get("status") == "pending" else None,
        )
        view["tweets"] = _get_task_result_snapshot(tid, load=True) if include_payload else []
        views.append(view)
    views.sort(key=lambda t: t["created_at"], reverse=True)
    return views


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
    _persist_force(task_id, full=status in ("done", "failed", "stopped"))


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


def update_comment_backfill_progress(task_id: str, progress: Optional[dict]) -> None:
    merged = {**_default_comment_backfill_progress(), **(progress or {})}
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["comment_backfill_progress"] = merged
        _touch(task)
    _persist(task_id)


def update_task_source_task_id(task_id: str, source_task_id: Optional[str]) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["source_task_id"] = source_task_id
        _touch(task)
    _persist_force(task_id, full=False)


def update_task_reply_collection_config(
    task_id: str,
    *,
    fetch_replies: bool,
    reply_depth: int,
) -> bool:
    from crawler import telemetry

    normalized_depth = max(1, int(reply_depth))

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        task["fetch_replies"] = fetch_replies
        task["reply_depth"] = normalized_depth
        _touch(task)
        status = task.get("status")
        phase = task.get("crawl_phase", "")

    telemetry.record_event(
        task_id,
        "task_reply_collection_updated",
        status=status,
        phase=phase,
        meta={
            "fetch_replies": fetch_replies,
            "reply_depth": normalized_depth,
        },
    )
    _persist_force(task_id, full=False)
    return True


def update_task_progress(task_id: str, current_page: int, tweets_so_far: list[dict]) -> None:
    from crawler import telemetry

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        prev_result = int(task.get("result_count", 0))
        prev_replies = int(task.get("replies_fetched", 0))
        prev_coverage = dict(task.get("time_coverage", {}))

    if len(tweets_so_far) < prev_result:
        replies_fetched, coverage = _summarize_tweets(tweets_so_far)
    else:
        new_tweets = tweets_so_far[prev_result:]
        delta_replies, delta_coverage = _summarize_tweets(new_tweets) if new_tweets else (0, {})
        replies_fetched = prev_replies + int(delta_replies)
        coverage = _merge_coverage(prev_coverage, delta_coverage)

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        prev_result = int(task.get("result_count", 0))
        prev_replies = int(task.get("replies_fetched", 0))
        task.update(
            {
                "current_page": current_page,
                "result_count": len(tweets_so_far),
                "replies_fetched": replies_fetched,
                "preview_tweets": _make_preview(tweets_so_far),
                "time_coverage": coverage,
            }
        )
        _set_task_result_locked(task_id, tweets_so_far)
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
    """更新预览和内存结果；仅对新增 tweet 做增量汇总，避免回复阶段反复全量扫描。"""
    from crawler import telemetry

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        prev_result = int(task.get("result_count", 0))
        prev_replies = int(task.get("replies_fetched", 0))
        prev_coverage = dict(task.get("time_coverage", {}))

    if len(tweets_for_preview) > prev_result:
        delta_replies, delta_coverage = _summarize_tweets(tweets_for_preview[prev_result:])
        replies_fetched = prev_replies + int(delta_replies)
        coverage = _merge_coverage(prev_coverage, delta_coverage)
    else:
        replies_fetched = prev_replies
        coverage = prev_coverage

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        prev_result = int(task.get("result_count", 0))
        task.update(
            {
                "current_page": current_page,
                "result_count": len(tweets_for_preview),
                "preview_tweets": _make_preview(tweets_for_preview),
                "replies_fetched": replies_fetched,
                "time_coverage": coverage,
            }
        )
        _set_task_result_locked(task_id, tweets_for_preview)
        _touch(task)
        delta_tweets = max(0, len(tweets_for_preview) - prev_result)
        delta_replies_telemetry = max(0, replies_fetched - prev_replies)
        phase = task.get("crawl_phase", "")
        status = task.get("status")
        risk_state = task.get("risk_state")
    telemetry.record_event(
        task_id,
        "preview_progress",
        phase=phase,
        page=current_page,
        delta_tweets=delta_tweets,
        delta_replies=delta_replies_telemetry,
        status=status,
        risk_state=risk_state,
        meta={"preview_count": len(tweets_for_preview)},
    )
    # 写入 10 分钟采集量分桶
    if delta_tweets > 0 or delta_replies_telemetry > 0:
        try:
            from api.services.crawl_volume_db import write_volume
            write_volume(delta_tweets=delta_tweets, delta_replies=delta_replies_telemetry)
        except Exception:
            pass
    _persist(task_id)



def set_task_seed_tweets(task_id: str, tweets_for_preview: list[dict], *, current_page: int = 0) -> None:
    """
    初始化任务种子帖子并强制落库完整结果。

    适用于评论补采等需要“先保存输入帖子，再异步执行”的任务，
    避免只写摘要时被节流吞掉，导致 task_results 为空。
    """
    from crawler import telemetry

    replies_fetched, coverage = _summarize_tweets(tweets_for_preview)

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        prev_result = int(task.get("result_count", 0))
        _set_task_result_locked(task_id, tweets_for_preview)
        task.update(
            {
                "current_page": current_page,
                "result_count": len(tweets_for_preview),
                "preview_tweets": _make_preview(tweets_for_preview),
                "replies_fetched": replies_fetched,
                "time_coverage": coverage,
            }
        )
        _touch(task)
        phase = task.get("crawl_phase", "")
        status = task.get("status")
        risk_state = task.get("risk_state")

    telemetry.record_event(
        task_id,
        "seed_tweets_ready",
        phase=phase,
        page=current_page,
        delta_tweets=max(0, len(tweets_for_preview) - prev_result),
        status=status,
        risk_state=risk_state,
        meta={"seed_count": len(tweets_for_preview)},
    )
    _persist_force(task_id, full=True)


def _normalize_task_post_id(tweet: dict) -> str:
    return str(tweet.get("id") or tweet.get("mid") or "").strip()


def update_task_reply_snapshot(
    task_id: str,
    tweet_id: str,
    replies: list[dict],
    *,
    comment_stats: Optional[dict] = None,
) -> bool:
    """
    按帖子维度幂等回写评论树，避免二级评论重复累计。

    优化：增量缓存 + 节流落盘（每 30 条或 30 秒触发完整持久化）
    """
    from crawler import telemetry
    from api.services.reply_tree import count_reply_tree_nodes

    normalized_tweet_id = str(tweet_id or "").strip()
    if not normalized_tweet_id:
        return False

    normalized_replies = normalize_json_value(replies)
    if not isinstance(normalized_replies, list):
        logger.warning("update_task_reply_snapshot 收到非列表 replies，已回退为空列表: task_id=%s", task_id)
        normalized_replies = []

    tweets_ref = _get_task_result_ref(task_id, load=True)
    if not tweets_ref:
        return False

    old_count = 0
    new_count = count_reply_tree_nodes(normalized_replies)
    updated = False

    for tweet in tweets_ref:
        if not isinstance(tweet, dict):
            continue
        if _normalize_task_post_id(tweet) != normalized_tweet_id:
            continue
        old_count = count_reply_tree_nodes(tweet.get("replies"))
        tweet["replies"] = normalized_replies
        if comment_stats is not None:
            tweet["comment_stats"] = normalize_json_value(comment_stats)
        updated = True
        break

    if not updated:
        return False

    # 增量更新缓存（避免每次都对全 tweets 走查）
    delta_replies = max(0, new_count - old_count)
    with _reply_summary_cache_lock:
        if task_id not in _reply_summary_cache:
            # 首次：全量计算
            replies_fetched, coverage = _summarize_tweets(tweets_ref)
            _reply_summary_cache[task_id] = {
                "replies_fetched": replies_fetched,
                "coverage": coverage,
            }
        else:
            # 增量更新
            cache = _reply_summary_cache[task_id]
            cache["replies_fetched"] = cache.get("replies_fetched", 0) + delta_replies
            # coverage 保持不变（仅在完整落盘时更新）

        replies_fetched = _reply_summary_cache[task_id]["replies_fetched"]
        coverage = _reply_summary_cache[task_id]["coverage"]

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return False
        task["replies_fetched"] = replies_fetched
        task["preview_tweets"] = _make_preview(tweets_ref)
        task["time_coverage"] = coverage
        _touch(task)
        phase = task.get("crawl_phase", "")
        status = task.get("status")
        risk_state = task.get("risk_state")
        page = task.get("current_page")

    telemetry.record_event(
        task_id,
        "reply_tree_synced",
        phase=phase,
        page=page,
        delta_replies=delta_replies,
        status=status,
        risk_state=risk_state,
        meta={
            "tweet_id": normalized_tweet_id,
            "old_reply_count": old_count,
            "new_reply_count": new_count,
        },
    )

    # 节流落盘：每 30 条评论或每 30 秒触发一次完整持久化
    import time
    now = time.monotonic()
    with _reply_summary_cache_lock:
        counter = _reply_persist_counter.get(task_id, 0) + 1
        _reply_persist_counter[task_id] = counter
        last_full = _reply_last_full_persist.get(task_id, 0.0)
        should_persist_full = counter >= 30 or (now - last_full) >= 30.0

    if should_persist_full:
        # 完整持久化：重新计算 coverage + 落盘
        replies_fetched, coverage = _summarize_tweets(tweets_ref)
        with _reply_summary_cache_lock:
            _reply_summary_cache[task_id] = {
                "replies_fetched": replies_fetched,
                "coverage": coverage,
            }
            _reply_persist_counter[task_id] = 0
            _reply_last_full_persist[task_id] = now
        with _tasks_lock:
            task = _tasks.get(task_id)
            if task:
                task["replies_fetched"] = replies_fetched
                task["time_coverage"] = coverage
        _persist(task_id, full=True)
    else:
        # 轻量持久化：只写 summary
        _persist(task_id, full=False)

    return True


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
        _set_task_result_locked(task_id, tweets)
        task.update(
            {
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
            }
        )
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
    _persist_force(task_id, full=True)


def update_task_stopped(task_id: str, tweets_so_far: list[dict], runtime_metrics: Optional[dict] = None) -> None:
    from crawler import telemetry

    replies_fetched, coverage = _summarize_tweets(tweets_so_far)

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        _set_task_result_locked(task_id, tweets_so_far)
        task.update(
            {
                "preview_tweets": _make_preview(tweets_so_far),
                "result_count": len(tweets_so_far),
                "status": "stopped",
                "quality_state": "interrupted",
                "runtime_metrics": runtime_metrics or {},
                "finished_at": _now_iso(),
                "risk_state": "none",
                "replies_fetched": replies_fetched,
                "time_coverage": coverage,
            }
        )
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
    _persist_force(task_id, full=True)


def update_task_error(task_id: str, error: str, runtime_metrics: Optional[dict] = None) -> None:
    from crawler import telemetry

    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task.update(
            {
                "status": "failed",
                "quality_state": "interrupted",
                "runtime_metrics": runtime_metrics or {},
                "error": error,
                "finished_at": _now_iso(),
            }
        )
        has_loaded_results = task_id in _loaded_task_results
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
    _persist_force(task_id, full=has_loaded_results)


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
        task.update(
            {
                "status": "paused",
                "risk_state": risk_state,
                "quality_state": "partial",
                "runtime_metrics": runtime_metrics or task.get("runtime_metrics", {}),
                "crawl_phase": phase,
            }
        )
        _touch(task)
    send_signal(task_id, "pause")
    telemetry.record_event(
        task_id,
        "task_risk_paused",
        status="paused",
        phase=phase,
        risk_state=risk_state,
    )
    _persist_force(task_id, full=True)


def update_task_debug_screenshot(task_id: str, screenshot_url: Optional[str]) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task["debug_screenshot"] = screenshot_url
        _touch(task)
    _persist(task_id)


def delete_task(task_id: str) -> bool:
    from crawler import telemetry

    removed = False
    with _tasks_lock:
        if task_id in _tasks:
            del _tasks[task_id]
            removed = True
        _task_results.pop(task_id, None)
        _loaded_task_results.discard(task_id)
    if not removed:
        return False

    clear_signal(task_id)
    clear_thread(task_id)
    with _persist_mark_lock:
        _persist_mark.pop(task_id, None)

    # 清理 reply 增量缓存
    with _reply_summary_cache_lock:
        _reply_summary_cache.pop(task_id, None)
        _reply_persist_counter.pop(task_id, None)
        _reply_last_full_persist.pop(task_id, None)

    telemetry.clear_task(task_id)

    # 清理其他模块级缓存
    try:
        from crawler import utils, reply_fetcher, circuit_breaker, browser_lifecycle
        # 清理 utils 中的暂停日志时间戳
        if hasattr(utils, '_PAUSE_LOG_TS'):
            utils._PAUSE_LOG_TS.pop(task_id, None)
        # 清理 reply_fetcher 中的登录缓存
        if hasattr(reply_fetcher, '_login_cache'):
            reply_fetcher._login_cache.pop(task_id, None)
        # 清理 circuit_breaker 中的断路器状态
        if hasattr(circuit_breaker, '_breakers'):
            circuit_breaker._breakers.pop(task_id, None)
        # 清理 browser_lifecycle 中的页面计数
        if hasattr(browser_lifecycle, '_page_counts'):
            browser_lifecycle._page_counts.pop(task_id, None)
    except Exception as cleanup_err:
        logger.debug(f"清理模块级缓存时出错（非致命）: {cleanup_err}")

    try:
        _get_db().delete_task(task_id)
    except Exception as e:
        logger.error(f"从数据库删除任务失败 task_id={task_id}: {e}")
    return True


# ─── 账号绑定管理 ──────────────────────────────────────────────────────────

def bind_account(task_id: str, account_id: str, account_alias: str) -> bool:
    """
    为任务绑定账号。

    返回：
        bool: 是否成功绑定
    """
    with _tasks_lock:
        if task_id not in _tasks:
            return False
        _tasks[task_id]["assigned_account_id"] = account_id
        _tasks[task_id]["account_alias"] = account_alias
        _touch(_tasks[task_id])
        _mark_persist(task_id)
        return True


def release_account(task_id: str) -> bool:
    """
    释放任务的账号绑定。

    返回：
        bool: 是否成功释放
    """
    with _tasks_lock:
        if task_id not in _tasks:
            return False
        _tasks[task_id]["assigned_account_id"] = None
        _tasks[task_id]["account_alias"] = None
        _touch(_tasks[task_id])
        _mark_persist(task_id)
        return True


def get_task_account(task_id: str) -> tuple[Optional[str], Optional[str]]:
    """
    获取任务绑定的账号。

    返回：
        (account_id, account_alias) 或 (None, None)
    """
    with _tasks_lock:
        if task_id not in _tasks:
            return None, None
        task = _tasks[task_id]
        return task.get("assigned_account_id"), task.get("account_alias")
