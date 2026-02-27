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
        self._queued_ids: set[str] = set()
        self._queued_order: list[str] = []
        self._executor: Optional[Callable[[str, dict], threading.Thread]] = None
        self._backend: SchedulerBackend = self._make_backend()
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

    def enqueue(self, task_id: str, payload: dict) -> bool:
        with self._lock:
            if task_id in self._running or task_id in self._queued_ids:
                return False
            self._queued_ids.add(task_id)
            self._queued_order.append(task_id)
            self._backend.put(ScheduledTask(task_id=task_id, payload=payload))
            return True

    def mark_done(self, task_id: str) -> None:
        with self._lock:
            self._running.pop(task_id, None)
            self._queued_ids.discard(task_id)
            if task_id in self._queued_order:
                self._queued_order = [tid for tid in self._queued_order if tid != task_id]

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

    def effective_worker_limit(self) -> int:
        return self._max_workers()

    def _dispatch_loop(self) -> None:
        while True:
            try:
                self._cleanup_dead_threads()
                if self._executor is None:
                    time.sleep(0.2)
                    continue
                if self._running_count() >= self._max_workers():
                    time.sleep(0.2)
                    continue

                item = self._backend.get(timeout=0.5)
                if not item:
                    continue

                with self._lock:
                    self._queued_ids.discard(item.task_id)
                    if item.task_id in self._queued_order:
                        self._queued_order = [tid for tid in self._queued_order if tid != item.task_id]
                    if item.task_id in self._running:
                        continue
                    thread = self._executor(item.task_id, item.payload)
                    self._running[item.task_id] = thread
            except Exception as e:
                logger.error(f"调度器循环异常: {e}", exc_info=True)
                time.sleep(0.5)

    def _cleanup_dead_threads(self) -> None:
        with self._lock:
            dead = [tid for tid, t in self._running.items() if not t.is_alive()]
            for tid in dead:
                self._running.pop(tid, None)

    def _running_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._running.values() if t.is_alive())


scheduler = TaskScheduler()
