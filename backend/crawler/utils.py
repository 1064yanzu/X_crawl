"""
爬虫公共工具模块

提取 x_searcher / reply_fetcher 中重复的工具函数，统一维护。
"""
import time
import random
import logging
from typing import Optional
from crawler.crawl_signals import StopSignal
from config import settings

logger = logging.getLogger(__name__)


def interruptible_sleep(seconds: float, task_id: Optional[str] = None) -> None:
    """
    可中断等待：长 sleep 会分片执行，期间可响应 pause/stop。
    """
    total = max(0.0, float(seconds))
    poll_ms = max(50, int(getattr(settings, "crawler_interrupt_poll_ms", 300)))
    step = poll_ms / 1000.0
    elapsed = 0.0
    while elapsed < total:
        if task_id:
            check_signal(task_id)
        remain = total - elapsed
        slice_s = min(step, remain)
        time.sleep(slice_s)
        elapsed += slice_s


def jittered_sleep(base_seconds: float, task_id: Optional[str] = None) -> None:
    """带随机扰动的等待（±20%），并可响应任务控制信号。"""
    base = max(0.0, float(base_seconds))
    if getattr(settings, "crawler_adaptive_wait_enabled", True):
        lower = max(0.2, float(getattr(settings, "crawler_page_interval_min", base or 0.2)))
        upper = max(lower, float(getattr(settings, "crawler_page_interval_max", max(base, lower))))
        base = min(max(base, lower), upper)
    jitter = base * 0.2
    actual = max(0.5, base + random.uniform(-jitter, jitter))
    interruptible_sleep(actual, task_id=task_id)


def check_signal(task_id: Optional[str]) -> None:
    """
    检查任务控制信号：
    - stop  → 抛出 StopSignal 异常，终止爬虫
    - pause → 轮询等待，直到信号变为 run（支持继续）
    - run   → 直接返回（正常）
    """
    if not task_id:
        return
    # 延迟导入避免循环引用
    import api.services.task_manager as _task_mgr

    while True:
        signal = _task_mgr.get_signal(task_id)
        if signal == "stop":
            raise StopSignal(f"任务 {task_id} 收到终止信号")
        elif signal == "pause":
            logger.info(f"任务 {task_id} 已暂停，等待继续信号...")
            interruptible_sleep(1.0)
        else:
            break


def merge_remaining(updated: list[dict], tweets: list[dict], start_idx: int) -> None:
    """将未处理的推文（无 replies）追加到 updated 列表中，用于 StopSignal 中断时保留完整数据"""
    for t in tweets[start_idx:]:
        t_copy = dict(t)
        t_copy.setdefault("replies", [])
        updated.append(t_copy)
