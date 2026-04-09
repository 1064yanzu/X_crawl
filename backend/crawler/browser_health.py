"""
浏览器健康检测工具

提供轻量级的浏览器健康检测函数，供 browser_lifecycle.py 心跳线程调用。

职责：
  - 内存压力检测（Chrome 进程树 RSS）
  - CDP 心跳检测（快速响应测试）
  - 综合健康判定
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

try:
    import psutil
except Exception:
    psutil = None

logger = logging.getLogger(__name__)

# Chrome 进程树 RSS 内存上限 (MB)，默认值；实际使用时优先从 settings.browser_memory_limit_mb 读取
MAX_MEMORY_MB = 2500.0


def get_browser_memory_mb(browser) -> Optional[float]:
    """获取浏览器主进程 + 所有子进程的总 RSS 内存 (MB)。"""
    if psutil is None:
        return None
    pid = getattr(browser, "process_id", None)
    if not pid:
        return None
    try:
        proc = psutil.Process(pid)
        total_rss = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                total_rss += child.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return total_rss / (1024 * 1024)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def is_memory_pressure(browser, threshold_mb: float = MAX_MEMORY_MB) -> bool:
    """检测浏览器进程树内存是否超过阈值。"""
    mem = get_browser_memory_mb(browser)
    if mem is None:
        return False
    return mem > threshold_mb
