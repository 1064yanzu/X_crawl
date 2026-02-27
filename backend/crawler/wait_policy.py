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
    return min(3.0, max(0.8, total * 0.2))


def compensation_probe_timeout(total_timeout: float) -> float:
    """补偿等待窗口。"""
    total = max(1.0, float(total_timeout))
    return max(2.5, min(12.0, total * 0.65))


def scroll_steps() -> int:
    wait = float(getattr(settings, "crawler_reply_wait", 4.0))
    if wait <= 2.0:
        return 3
    if wait <= 4.0:
        return 4
    return 5


def scroll_pause_seconds() -> float:
    wait = float(getattr(settings, "crawler_reply_wait", 4.0))
    return max(0.16, min(0.7, wait * 0.18))


def scroll_step_pause(task_id: str | None = None) -> None:
    base = scroll_pause_seconds()
    actual = max(0.1, base + random.uniform(-0.08, 0.12))
    interruptible_sleep(actual, task_id=task_id)


def before_scroll_wait(task_id: str | None = None) -> None:
    """
    翻页前的轻量等待。
    只保留短窗口让 DOM 稳定，避免旧逻辑中的长等待放大。
    """
    base = max(0.25, min(2.0, float(getattr(settings, "crawler_reply_wait", 4.0)) * 0.35))
    interruptible_sleep(base, task_id=task_id)
    # 基线翻页节奏仍保留随机抖动，但由全局自适应区间约束
    jittered_sleep(float(getattr(settings, "crawler_page_interval", 4.0)), task_id=task_id)

