"""
回复抓取等待策略。

核心思路：
- 先短时间抢包（低延迟）
- 未命中再走补偿窗口（保覆盖）
- 翻页滚动使用可中断、短间隔策略
"""
from __future__ import annotations

import random

from config import settings
from crawler.utils import interruptible_sleep, jittered_sleep


def quick_probe_timeout(total_timeout: float) -> float:
    """首轮抢包窗口。"""
    total = max(1.0, float(total_timeout))
    return min(2.0, max(0.5, total * 0.12))


def compensation_probe_timeout(total_timeout: float) -> float:
    """补偿等待窗口。"""
    total = max(1.0, float(total_timeout))
    return max(2.0, min(8.0, total * 0.4))


def scroll_steps() -> int:
    """Reply scroll step count - fixed at 2 for efficiency."""
    return 2


def scroll_pause_seconds() -> float:
    """Minimal pause between scroll steps."""
    return 0.08


def scroll_step_pause(task_id: str | None = None) -> None:
    base = scroll_pause_seconds()
    actual = max(0.05, base + random.uniform(-0.02, 0.04))
    interruptible_sleep(actual, task_id=task_id)


def before_scroll_wait(task_id: str | None = None) -> None:
    """
    翻页前的轻量等待：仅让 DOM 稳定，尽可能短。
    """
    interruptible_sleep(0.05, task_id=task_id)
