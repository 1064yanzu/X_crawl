"""
任务调度器（先内置内存队列，预留 Redis 后端扩展点）。
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScheduledTask:
    task_id: str
    payload: dict
    platform: str = "x"


class SchedulerBackend(Protocol):
    def put(self, item: ScheduledTask) -> None: ...
    def get(self, timeout: float = 0.5) -> Optional[ScheduledTask]: ...
    def size(self) -> int: ...


class MemoryQueueBackend:
    def __init__(self) -> None:
        self._q: queue.Queue[ScheduledTask] = queue.Queue()

    def put(self, item: ScheduledTask) -> None:
        self._q.put(item)

    def get(self, timeout: float = 0.5) -> Optional[ScheduledTask]:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def size(self) -> int:
        return self._q.qsize()


class RedisQueueBackend:
    """
    Redis 队列扩展占位（后续实现）。
    当前不启用实际 Redis 依赖，避免部署强耦合。
    """

    def put(self, item: ScheduledTask) -> None:  # pragma: no cover - 预留接口
        raise NotImplementedError("Redis 调度后端尚未实现")

    def get(self, timeout: float = 0.5) -> Optional[ScheduledTask]:  # pragma: no cover
        raise NotImplementedError("Redis 调度后端尚未实现")

    def size(self) -> int:  # pragma: no cover
        return 0


class TaskScheduler:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._running: dict[str, threading.Thread] = {}
        self._running_platforms: dict[str, str] = {}  # task_id -> platform
        self._queued_ids: set[str] = set()
        self._queued_order: list[str] = []
        self._queued_platforms: dict[str, str] = {}  # task_id -> platform
        self._executor: Optional[Callable[[str, dict], threading.Thread]] = None
        self._backend: SchedulerBackend = self._make_backend()
        self._pending_items: list[ScheduledTask] = []  # 暂时无法调度的任务（平台槽满）
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop,
            daemon=True,
            name="task-scheduler-dispatcher",
        )
        self._dispatch_thread.start()

    def _make_backend(self) -> SchedulerBackend:
        backend = (settings.scheduler_backend or "memory").strip().lower()
        if backend == "redis":
            logger.warning("配置了 scheduler_backend=redis，但 Redis 后端尚未实现，自动回退 memory")
        return MemoryQueueBackend()

    def register_executor(self, executor: Callable[[str, dict], threading.Thread]) -> None:
        self._executor = executor

    def reconfigure_backend(self) -> None:
        with self._lock:
            # 仅允许在队列空闲时切换，避免丢任务
            if self._running or self._backend.size() > 0:
                logger.warning("调度器正在处理任务，暂不切换后端配置")
                return
            self._backend = self._make_backend()
            logger.info(f"调度后端已刷新: {settings.scheduler_backend}")

    def enqueue(self, task_id: str, payload: dict, platform: str = "x") -> bool:
        with self._lock:
            if task_id in self._running or task_id in self._queued_ids:
                return False
            self._queued_ids.add(task_id)
            self._queued_order.append(task_id)
            self._queued_platforms[task_id] = platform
            self._backend.put(ScheduledTask(task_id=task_id, payload=payload, platform=platform))
            return True

    def mark_done(self, task_id: str) -> None:
        with self._lock:
            self._running.pop(task_id, None)
            self._running_platforms.pop(task_id, None)
            self._queued_ids.discard(task_id)
            self._queued_platforms.pop(task_id, None)
            if task_id in self._queued_order:
                self._queued_order = [tid for tid in self._queued_order if tid != task_id]
            pending_count = len(self._pending_items)
            running_count = self._running_count()
            logger.info(
                "调度器 mark_done: task=%s, 剩余运行=%d, pending队列=%d, backend队列=%d",
                task_id[:8], running_count, pending_count, self._backend.size(),
            )

    def is_running(self, task_id: str) -> bool:
        with self._lock:
            t = self._running.get(task_id)
            return bool(t and t.is_alive())

    def queue_size(self) -> int:
        return self._backend.size()

    def running_count(self) -> int:
        return self._running_count()

    def queued_task_ids(self) -> list[str]:
        with self._lock:
            return [tid for tid in self._queued_order if tid in self._queued_ids]

    def _max_workers(self) -> int:
        configured = max(1, int(settings.crawler_max_concurrent_tasks))
        try:
            from crawler.resource_guard import effective_worker_limit

            return effective_worker_limit(configured)
        except Exception:
            return configured

    def _cross_platform_concurrent(self) -> bool:
        return bool(getattr(settings, "crawler_cross_platform_concurrent", True))

    def _platform_running_count(self, platform: str) -> int:
        with self._lock:
            return sum(
                1 for tid, p in self._running_platforms.items()
                if p == platform and tid in self._running and self._running[tid].is_alive()
            )

    def _x_account_worker_limit(self) -> int:
        configured = self._max_workers()
        if not bool(getattr(settings, "account_pool_enabled", True)):
            return configured

        try:
            from crawler.account_pool import get_pool
            from crawler.account_dispatcher import get_dispatcher

            active_accounts = max(0, int(get_pool().get_active_account_count()))
            if active_accounts <= 0:
                return configured

            active_assignments = max(0, int(get_dispatcher().active_assignment_count()))
            running_x = self._platform_running_count("x")
            paused_reserved = max(0, active_assignments - running_x)
            return max(0, min(configured, active_accounts - paused_reserved))
        except Exception:
            return configured

    def _can_dispatch(self, platform: str) -> bool:
        """判断指定平台是否可以调度新任务。"""
        max_w = self._x_account_worker_limit() if platform == "x" else self._max_workers()
        total_running = self._running_count()

        if not self._cross_platform_concurrent():
            # 关闭跨平台并发时，退化为全局串行
            return total_running < max_w

        # 跨平台并发：每个平台独占自己的并发槽，不同平台可同时运行
        # 每个平台最多运行 max_w 个任务
        platform_running = self._platform_running_count(platform)
        return platform_running < max_w

    def effective_worker_limit(self) -> int:
        return self._max_workers()

    def cross_platform_concurrent(self) -> bool:
        return self._cross_platform_concurrent()

    def _dispatch_loop(self) -> None:
        while True:
            try:
                self._cleanup_dead_threads()
                if self._executor is None:
                    time.sleep(0.2)
                    continue

                # 先尝试从 pending_items 中调度之前因平台槽满被暂缓的任务
                dispatched_from_pending = self._try_dispatch_pending()

                # ── 批量取出所有待调度任务，一次性分发，避免串行阻塞 ──
                batch: list[ScheduledTask] = []
                while True:
                    item = self._backend.get(timeout=0.5 if not batch else 0.01)
                    if item is None:
                        break
                    batch.append(item)

                if not batch:
                    if not dispatched_from_pending:
                        time.sleep(0.1)
                    continue

                for item in batch:
                    # 检查该任务所在平台是否可调度
                    if not self._can_dispatch(item.platform):
                        # 平台槽满，放入 pending 等待
                        with self._lock:
                            self._pending_items.append(item)
                        continue

                    self._do_dispatch(item)
            except Exception as e:
                logger.error(f"调度器循环异常: {e}", exc_info=True)
                time.sleep(0.5)

    def _try_dispatch_pending(self) -> bool:
        """尝试从 pending 列表中找到可调度的任务并执行。"""
        dispatched = False
        with self._lock:
            if self._pending_items:
                logger.debug(
                    "_try_dispatch_pending: pending=%d, running=%d, items=%s",
                    len(self._pending_items), self._running_count(),
                    [f"{it.task_id[:8]}({it.platform})" for it in self._pending_items],
                )
            still_pending: list[ScheduledTask] = []
            for item in self._pending_items:
                if item.task_id in self._running:
                    # 已经在运行了（不应发生），丢弃
                    continue
                if self._can_dispatch(item.platform):
                    self._do_dispatch_locked(item)
                    dispatched = True
                else:
                    still_pending.append(item)
            self._pending_items = still_pending
        return dispatched

    def _do_dispatch(self, item: ScheduledTask) -> None:
        with self._lock:
            self._do_dispatch_locked(item)

    def _do_dispatch_locked(self, item: ScheduledTask) -> None:
        """在持有 _lock 的情况下执行调度（内部方法）。"""
        self._queued_ids.discard(item.task_id)
        self._queued_platforms.pop(item.task_id, None)
        if item.task_id in self._queued_order:
            self._queued_order = [tid for tid in self._queued_order if tid != item.task_id]
        if item.task_id in self._running:
            return
        thread = self._executor(item.task_id, item.payload)
        self._running[item.task_id] = thread
        self._running_platforms[item.task_id] = item.platform
        logger.info(
            "调度器启动任务: task_id=%s, platform=%s, 当前运行=%s",
            item.task_id[:8], item.platform, self._running_count(),
        )

    def _cleanup_dead_threads(self) -> None:
        with self._lock:
            dead = [tid for tid, t in self._running.items() if not t.is_alive()]
            for tid in dead:
                self._running.pop(tid, None)
                self._running_platforms.pop(tid, None)

    def _running_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._running.values() if t.is_alive())


scheduler = TaskScheduler()
