"""
爬虫公共工具模块

提取 x_searcher / reply_fetcher 中重复的工具函数，统一维护。
"""
import time
import math
import random
import logging
import threading
from typing import Optional
from crawler.browser import maybe_cleanup_stale_linux_browsers
from crawler.crawl_signals import StopSignal
from crawler.resource_guard import get_throttle_multiplier
from crawler.runtime_metrics import bump_metric
from config import settings

logger = logging.getLogger(__name__)
_PAUSE_LOG_LOCK = threading.Lock()
_PAUSE_LOG_TS: dict[str, float] = {}
_PAUSE_LOG_INTERVAL_SEC = 15.0


def interruptible_sleep(seconds: float, task_id: Optional[str] = None) -> None:
    """
    可中断等待：长 sleep 会分片执行，期间可响应 pause/stop。
    """
    total = max(0.0, float(seconds))
    poll_ms = max(50, int(getattr(settings, "crawler_interrupt_poll_ms", 300)))
    step = poll_ms / 1000.0
    elapsed = 0.0
    # 每 10秒执行一次清理检查，而不是每次 sleep 片段都检查
    cleanup_interval = 10.0
    last_cleanup = 0.0
    while elapsed < total:
        if task_id:
            check_signal(task_id)
        if elapsed - last_cleanup >= cleanup_interval:
            maybe_cleanup_stale_linux_browsers(reason="interruptible_sleep")
            last_cleanup = elapsed
        remain = total - elapsed
        slice_s = min(step, remain)
        time.sleep(slice_s)
        elapsed += slice_s


def jittered_sleep(base_seconds: float, task_id: Optional[str] = None, fast_mode: bool = False) -> None:
    """带随机扰动的等待（±20%），并可响应任务控制信号。
    
    fast_mode=True 时跳过自适应等待和节流，直接使用 base_seconds 的 50-80%。
    """
    base = max(0.0, float(base_seconds))
    
    if fast_mode:
        # 快速模式：缩短等待，不做自适应/节流
        actual = base * random.uniform(0.5, 0.8)
        interruptible_sleep(max(0.3, actual), task_id=task_id)
        return
    
    if getattr(settings, "crawler_adaptive_wait_enabled", True):
        lower = max(0.2, float(getattr(settings, "crawler_page_interval_min", base or 0.2)))
        upper = max(lower, float(getattr(settings, "crawler_page_interval_max", max(base, lower))))
        base = min(max(base, lower), upper)
    throttle_factor, pressure_state = get_throttle_multiplier()
    if throttle_factor > 1.0:
        base *= throttle_factor
        if task_id:
            bump_metric(task_id, "resource_throttle_hits")
            if pressure_state == "critical":
                bump_metric(task_id, "resource_critical_hits")
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
            with _PAUSE_LOG_LOCK:
                _PAUSE_LOG_TS.pop(task_id, None)
            raise StopSignal(f"任务 {task_id} 收到终止信号")
        elif signal == "pause":
            now = time.monotonic()
            should_log = False
            with _PAUSE_LOG_LOCK:
                last = _PAUSE_LOG_TS.get(task_id, 0.0)
                if now - last >= _PAUSE_LOG_INTERVAL_SEC:
                    _PAUSE_LOG_TS[task_id] = now
                    should_log = True
            if should_log:
                logger.info(f"任务 {task_id} 已暂停，等待继续信号...")
            interruptible_sleep(1.0)
        else:
            with _PAUSE_LOG_LOCK:
                _PAUSE_LOG_TS.pop(task_id, None)
            break


def merge_remaining(updated: list[dict], tweets: list[dict], start_idx: int) -> None:
    """将未处理的推文（无 replies）追加到 updated 列表中，用于 StopSignal 中断时保留完整数据"""
    for t in tweets[start_idx:]:
        t_copy = dict(t)
        t_copy.setdefault("replies", [])
        updated.append(t_copy)


def lognormal_sleep(
    mean_seconds: float,
    sigma: float = 0.4,
    *,
    floor: float = 0.1,
    ceiling: float = 60.0,
    task_id: Optional[str] = None,
) -> None:
    """对数正态分布等待：比 uniform 更贴近真人操作时间分布（多数快，长尾慢）。

    mu = ln(mean) - sigma^2/2，使得期望值 = mean_seconds。
    """
    mu = math.log(max(0.01, float(mean_seconds))) - sigma ** 2 / 2
    sample = math.exp(mu + sigma * random.gauss(0, 1))
    actual = max(float(floor), min(float(ceiling), sample))
    interruptible_sleep(actual, task_id=task_id)
