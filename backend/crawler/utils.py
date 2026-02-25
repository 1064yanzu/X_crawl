"""
爬虫公共工具模块

提取 x_searcher / reply_fetcher 中重复的工具函数，统一维护。
"""
import time
import random
import logging
from typing import Optional
from crawler.crawl_signals import StopSignal

logger = logging.getLogger(__name__)


def jittered_sleep(base_seconds: float) -> None:
    """带随机扰动的等待（±20%），模拟人工操作节奏"""
    jitter = base_seconds * 0.2
    actual = base_seconds + random.uniform(-jitter, jitter)
    time.sleep(max(0.5, actual))


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
            time.sleep(1)
        else:
            break


def merge_remaining(updated: list[dict], tweets: list[dict], start_idx: int) -> None:
    """将未处理的推文（无 replies）追加到 updated 列表中，用于 StopSignal 中断时保留完整数据"""
    for t in tweets[start_idx:]:
        t_copy = dict(t)
        t_copy.setdefault("replies", [])
        updated.append(t_copy)
