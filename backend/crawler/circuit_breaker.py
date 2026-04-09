"""
全局断路器：检测 X 错误风暴并统一协调所有 worker 冷却。

问题场景：
  多个 reply_worker 并行时，每个 tab 独立遭遇 transient_error，
  各自执行重试+截图+冷却，导致：
  1. CDP 命令堆积（截图是重量级 CDP 命令）
  2. 同一任务的错误计数被多线程同时递增，过早触发冻结
  3. 所有 worker 同时陷入无效重试循环

解决思路：
  维护一个按 task_id 分组的滑动窗口，在窗口内错误次数超过阈值时
  "熔断"该任务，所有相关 worker 在 acquire_permission 时被阻塞等待，
  直到冷却期结束。

使用方式（在 navigate_with_retry / reply_fetcher 中）：
  from crawler.circuit_breaker import get_breaker

  breaker = get_breaker()
  breaker.acquire_permission(task_id)  # 错误风暴时自动阻塞等待冷却
  ...
  breaker.record_error(task_id)        # 记录一次错误
  breaker.record_success(task_id)      # 成功后重置
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 滑动窗口参数
_WINDOW_SEC = 30.0         # 观察窗口长度（秒）
_TRIP_THRESHOLD = 6        # 窗口内错误次数超过此值时熔断
_COOLDOWN_SEC = 15.0       # 熔断后统一冷却时间（秒）
_MAX_COOLDOWN_SEC = 60.0   # 最大冷却时间（连续熔断时递增）


class _TaskBreaker:
    """单个任务的断路器状态。"""

    def __init__(self):
        self.errors: list[float] = []           # 错误时间戳列表（滑动窗口）
        self.tripped_until: float = 0.0         # 熔断解除时间（monotonic）
        self.consecutive_trips: int = 0         # 连续熔断次数（用于递增冷却）


class CircuitBreaker:
    """全局断路器：按 task_id 分组管理。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._breakers: dict[str, _TaskBreaker] = {}

    def _get_or_create(self, task_id: str) -> _TaskBreaker:
        if task_id not in self._breakers:
            self._breakers[task_id] = _TaskBreaker()
        return self._breakers[task_id]

    def record_error(self, task_id: Optional[str]) -> None:
        """记录一次错误，可能触发熔断。"""
        if not task_id:
            return
        now = time.monotonic()
        with self._condition:
            tb = self._get_or_create(task_id)
            tb.errors.append(now)
            # 清理过期条目
            cutoff = now - _WINDOW_SEC
            tb.errors = [t for t in tb.errors if t > cutoff]

            # 检查是否需要熔断
            if len(tb.errors) >= _TRIP_THRESHOLD and now >= tb.tripped_until:
                tb.consecutive_trips += 1
                cooldown = min(
                    _COOLDOWN_SEC * tb.consecutive_trips,
                    _MAX_COOLDOWN_SEC,
                )
                tb.tripped_until = now + cooldown
                tb.errors.clear()  # 清空窗口，避免冷却结束后立即再次熔断
                logger.warning(
                    "[CircuitBreaker] task=%s 触发熔断"
                    "（窗口内 %d 次错误，连续第 %d 次），"
                    "所有 worker 冷却 %.0fs",
                    task_id[:8], _TRIP_THRESHOLD,
                    tb.consecutive_trips, cooldown,
                )
                self._condition.notify_all()

    def record_success(self, task_id: Optional[str]) -> None:
        """成功后重置连续熔断计数。"""
        if not task_id:
            return
        with self._lock:
            tb = self._breakers.get(task_id)
            if tb and tb.consecutive_trips > 0:
                tb.consecutive_trips = 0
                tb.errors.clear()

    def acquire_permission(self, task_id: Optional[str]) -> None:
        """获取操作许可。如果任务正在熔断中，阻塞等待直到冷却结束。"""
        if not task_id:
            return
        with self._condition:
            tb = self._breakers.get(task_id)
            if not tb:
                return
            while True:
                now = time.monotonic()
                remaining = tb.tripped_until - now
                if remaining <= 0:
                    return
                # 阻塞等待（可被 notify_all 唤醒以重新检查）
                self._condition.wait(timeout=min(remaining, 2.0))

    def cleanup(self, task_id: str) -> None:
        """任务结束后清理状态。"""
        with self._lock:
            self._breakers.pop(task_id, None)


# ─── 全局单例 ───────────────────────────────────────────────────────────────

_breaker: Optional[CircuitBreaker] = None
_breaker_lock = threading.Lock()


def get_breaker() -> CircuitBreaker:
    """获取全局断路器单例。"""
    global _breaker
    if _breaker is None:
        with _breaker_lock:
            if _breaker is None:
                _breaker = CircuitBreaker()
    return _breaker
