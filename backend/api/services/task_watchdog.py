"""
任务看门狗（watchdog）

监控两类问题：
1. 长时间无进展的 comment_backfill 任务（stale 检测 + 自动重排）
2. comment_backfill_group 任务的评论抓取速率低于阈值时发出告警并尝试自愈
"""
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

# ── 速率采样状态 ──────────────────────────────────────────────
# key = task_id, value = (timestamp_mono, replies_fetched)
_rate_samples: dict[str, tuple[float, int]] = {}
_rate_samples_lock = threading.Lock()

# 速率告警的冷却时间（防止反复告警）
_rate_alert_cooldown: dict[str, float] = {}
_RATE_ALERT_COOLDOWN_SEC = 120.0  # 同一任务最多 2 分钟告警一次


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


# ── 评论速率监控 ──────────────────────────────────────────────

def _min_reply_rate_per_minute() -> int:
    """每分钟最低评论抓取速率阈值（低于此值触发告警）。"""
    return max(1, int(getattr(settings, "crawler_watchdog_min_reply_rate", 1000)))


def _check_group_reply_rates(task_manager) -> None:
    """
    检查所有运行中的 comment_backfill_group 任务的评论抓取速率。

    逻辑：每次调用时采样当前 replies_fetched，与上次采样对比，
    计算 replies/minute。低于阈值则记录告警日志并触发自愈。
    """
    now_mono = time.monotonic()
    min_rate = _min_reply_rate_per_minute()

    with task_manager._tasks_lock:
        group_tasks = [
            copy.deepcopy(t)
            for t in task_manager._tasks.values()
            if str(t.get("task_kind") or "") == "comment_backfill_group"
            and str(t.get("status") or "") == "running"
        ]

    for task in group_tasks:
        task_id = str(task.get("task_id") or "")
        if not task_id:
            continue
        current_replies = int(task.get("replies_fetched", 0) or 0)

        with _rate_samples_lock:
            prev = _rate_samples.get(task_id)
            _rate_samples[task_id] = (now_mono, current_replies)

        if prev is None:
            # 首次采样，跳过（需要两个采样点才能计算速率）
            continue

        prev_ts, prev_replies = prev
        elapsed_sec = now_mono - prev_ts
        if elapsed_sec < 30:
            # 采样间隔太短，不准确
            continue

        delta_replies = current_replies - prev_replies
        rate_per_min = delta_replies / (elapsed_sec / 60.0) if elapsed_sec > 0 else 0

        concurrency = int(task.get("concurrency", 1) or 1)
        logger.info(
            "[watchdog] 速率采样: task=%s 并发=%d 评论增量=%d 间隔=%.0fs 速率=%.0f条/分",
            task_id[:8], concurrency, delta_replies, elapsed_sec, rate_per_min,
        )

        if rate_per_min < min_rate and delta_replies >= 0:
            # 检查告警冷却
            last_alert = _rate_alert_cooldown.get(task_id, 0.0)
            if now_mono - last_alert < _RATE_ALERT_COOLDOWN_SEC:
                continue
            _rate_alert_cooldown[task_id] = now_mono

            logger.warning(
                "[watchdog] 评论抓取速率过低: task=%s 速率=%.0f条/分 (阈值=%d) 并发=%d，尝试自愈",
                task_id[:8], rate_per_min, min_rate, concurrency,
            )
            _try_heal_slow_group(task_id, task, rate_per_min=rate_per_min, concurrency=concurrency)


def _try_heal_slow_group(
    task_id: str,
    task: dict,
    *,
    rate_per_min: float,
    concurrency: int,
) -> None:
    """
    尝试自愈速率过低的 comment_backfill_group 任务。

    策略：
    1. 速率 > 0 但低于阈值：记录告警，暂不自动重启（可能是自然变慢）
    2. 速率 == 0（完全无产出）：检查是否卡住了，如果 heartbeat 超时则重启
    """
    from api.services import task_manager

    if rate_per_min > 0:
        # 有产出但较慢 — 仅告警，不自动重启（避免频繁打断正在进行的抓取）
        task_manager.update_task_phase(
            task_id,
            f"⚠ 抓取速率较低（{rate_per_min:.0f}条/分），正在继续抓取中...",
        )
        logger.warning(
            "[watchdog] task=%s 速率偏低但仍有产出(%.0f/min)，暂不干预",
            task_id[:8], rate_per_min,
        )
        return

    # 速率 == 0：可能完全卡住了
    now = datetime.now(timezone.utc)
    heartbeat = _parse_iso(task.get("last_event_at"))
    if heartbeat is None:
        return

    idle_sec = (now - heartbeat).total_seconds()
    if idle_sec < 300:  # 5 分钟内没有产出可以容忍（可能在初始化/导航）
        logger.info(
            "[watchdog] task=%s 速率为0但idle仅%.0fs，暂不干预",
            task_id[:8], idle_sec,
        )
        return

    # 超过 5 分钟零产出 → 执行自愈：停止并重启
    logger.warning(
        "[watchdog] task=%s 零产出超过%.0f秒，执行自愈重启",
        task_id[:8], idle_sec,
    )
    _heal_stale_task(task, idle_sec=idle_sec)


def clear_rate_samples(task_id: str) -> None:
    """任务结束时清理速率采样数据。"""
    with _rate_samples_lock:
        _rate_samples.pop(task_id, None)
    _rate_alert_cooldown.pop(task_id, None)


# ── 主入口 ──────────────────────────────────────────────────

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

        # ── 1. 原有逻辑：stale comment_backfill 任务检测 ──
        candidates: list[tuple[dict, float]] = []
        with task_manager._tasks_lock:
            for task in task_manager._tasks.values():
                snapshot = copy.deepcopy(task)
                stale, idle_sec = _is_stale_comment_backfill(snapshot, now=now)
                if stale:
                    candidates.append((snapshot, idle_sec))

        for task, idle_sec in candidates:
            _heal_stale_task(task, idle_sec=idle_sec)

        # ── 2. 新增：comment_backfill_group 速率监控 ──
        _check_group_reply_rates(task_manager)

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

    # 对 comment_backfill_group 直接执行重启（不再检查 _is_stale_comment_backfill，
    # 因为它只匹配 comment_backfill 类型）
    task_kind = str(latest.get("task_kind") or "")
    if task_kind == "comment_backfill":
        stale, current_idle_sec = _is_stale_comment_backfill(latest, now=datetime.now(timezone.utc))
        if not stale:
            return
        idle_sec = current_idle_sec

    idle_minutes = max(1, int(round(idle_sec / 60.0)))
    queue_id = str(latest.get("queue_id") or "").strip() or None
    logger.warning(
        "检测到长时间无进展的任务，准备自动重排: task_id=%s kind=%s idle=%dmin status=%s queue=%s thread_alive=%s",
        task_id[:8],
        task_kind,
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

    # 清理速率采样数据
    clear_rate_samples(task_id)

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
