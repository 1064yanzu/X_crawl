"""
任务运行指标采集器（线程安全）。

按 task_id 聚合搜索/回复链路关键指标，供任务结果返回与持久化。
"""
from __future__ import annotations

import threading
from copy import deepcopy


_DEFAULT_METRICS = {
    "search_packet_timeouts": 0,
    "search_api_blocked_hits": 0,
    "reply_packet_timeouts": 0,
    "soft_retries": 0,
    "hard_refreshes": 0,
    "risk_hits": 0,
    "empty_pages": 0,
    "resource_throttle_hits": 0,
    "resource_critical_hits": 0,
}

_lock = threading.RLock()
_store: dict[str, dict] = {}


def start_task_metrics(task_id: str) -> None:
    with _lock:
        _store[task_id] = dict(_DEFAULT_METRICS)


def bump_metric(task_id: str | None, key: str, delta: int = 1) -> None:
    if not task_id or delta == 0:
        return
    with _lock:
        target = _store.setdefault(task_id, dict(_DEFAULT_METRICS))
        target[key] = int(target.get(key, 0)) + int(delta)


def get_metrics(task_id: str | None) -> dict:
    if not task_id:
        return dict(_DEFAULT_METRICS)
    with _lock:
        data = _store.get(task_id, _DEFAULT_METRICS)
        return deepcopy(data)


def clear_metrics(task_id: str | None) -> None:
    if not task_id:
        return
    with _lock:
        _store.pop(task_id, None)
