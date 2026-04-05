"""
DFS 回复阶段检查点缓冲器。

将“每条回复进度都落盘”改为“批次/时间窗落盘”，
在保证可恢复性的前提下减少磁盘 I/O。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from config import settings
from crawler.checkpoint import save_checkpoint, save_checkpoint_sync


@dataclass
class _ReplyCheckpointState:
    keyword: str
    product: str
    tweets_so_far: list[dict]
    next_cursor: Optional[str]
    page_fetched: int
    extra: Optional[dict]
    pending_items: int
    last_flush_at: float


_lock = threading.RLock()
_states: dict[str, _ReplyCheckpointState] = {}


def _batch_size() -> int:
    return max(1, int(getattr(settings, "crawler_checkpoint_reply_batch", 3)))


def _flush_interval() -> float:
    return max(0.2, float(getattr(settings, "crawler_checkpoint_flush_interval_sec", 4.0)))


def stage_reply_checkpoint(
    *,
    task_id: str,
    keyword: str,
    product: str,
    tweets_so_far: list[dict],
    next_cursor: Optional[str],
    page_fetched: int,
    extra: Optional[dict] = None,
) -> bool:
    """
    记录一次 DFS 回复进度并按策略决定是否落盘。

    Returns:
        True  表示本次触发了落盘
        False 表示仅缓冲，尚未落盘
    """
    now = time.monotonic()
    with _lock:
        state = _states.get(task_id)
        if state is None:
            state = _ReplyCheckpointState(
                keyword=keyword,
                product=product,
                tweets_so_far=tweets_so_far,
                next_cursor=next_cursor,
                page_fetched=page_fetched,
                extra=extra,
                pending_items=0,
                last_flush_at=now,
            )
            _states[task_id] = state

        state.keyword = keyword
        state.product = product
        state.tweets_so_far = tweets_so_far
        state.next_cursor = next_cursor
        state.page_fetched = page_fetched
        state.extra = extra
        state.pending_items += 1

        should_flush = (
            state.pending_items >= _batch_size()
            or (now - state.last_flush_at) >= _flush_interval()
        )
        if not should_flush:
            return False

        save_checkpoint(
            task_id=task_id,
            keyword=state.keyword,
            product=state.product,
            tweets_so_far=state.tweets_so_far,
            next_cursor=state.next_cursor,
            page_fetched=state.page_fetched,
            extra=state.extra,
        )
        state.pending_items = 0
        state.last_flush_at = now
        return True


def flush_reply_checkpoint(task_id: str) -> bool:
    """
    强制刷新指定任务的缓冲检查点。

    Returns:
        True  = 刷新成功
        False = 无待刷状态
    """
    with _lock:
        state = _states.get(task_id)
        if state is None:
            return False

        save_checkpoint_sync(
            task_id=task_id,
            keyword=state.keyword,
            product=state.product,
            tweets_so_far=state.tweets_so_far,
            next_cursor=state.next_cursor,
            page_fetched=state.page_fetched,
            extra=state.extra,
        )
        state.pending_items = 0
        state.last_flush_at = time.monotonic()
        return True


def clear_reply_checkpoint(task_id: str) -> None:
    with _lock:
        _states.pop(task_id, None)
