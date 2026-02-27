"""任务实时遥测与事件总线。"""
from __future__ import annotations

import threading
import time
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

_EVENT_BUFFER_SIZE = 300
_RATE_WINDOWS = (15, 60)

_lock = threading.RLock()
_store: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure(task_id: str) -> dict:
    state = _store.get(task_id)
    if state is None:
        now = time.monotonic()
        state = {
            "created_mono": now,
            "last_mono": now,
            "cursor": 0,
            "events": deque(maxlen=_EVENT_BUFFER_SIZE),
            "tweet_deltas": deque(),
            "reply_deltas": deque(),
            "latest_action": None,
        }
        _store[task_id] = state
    return state


def init_task(task_id: str, *, status: str = "pending", phase: str = "") -> None:
    with _lock:
        _ensure(task_id)
    record_event(task_id, "task_initialized", status=status, phase=phase or "任务已初始化")


def clear_task(task_id: Optional[str]) -> None:
    if not task_id:
        return
    with _lock:
        _store.pop(task_id, None)


def _compact_rate_queue(dq: deque, now_mono: float, horizon: int = 60) -> None:
    cutoff = now_mono - max(1, horizon)
    while dq and dq[0][0] < cutoff:
        dq.popleft()


def record_event(
    task_id: Optional[str],
    event_type: str,
    *,
    phase: str = "",
    page: Optional[int] = None,
    delta_tweets: int = 0,
    delta_replies: int = 0,
    status: Optional[str] = None,
    risk_state: Optional[str] = None,
    meta: Optional[dict] = None,
) -> Optional[dict]:
    if not task_id:
        return None

    now_mono = time.monotonic()
    with _lock:
        state = _ensure(task_id)
        state["cursor"] += 1
        eid = state["cursor"]
        state["last_mono"] = now_mono

        if delta_tweets:
            state["tweet_deltas"].append((now_mono, int(delta_tweets)))
        if delta_replies:
            state["reply_deltas"].append((now_mono, int(delta_replies)))

        _compact_rate_queue(state["tweet_deltas"], now_mono)
        _compact_rate_queue(state["reply_deltas"], now_mono)

        event = {
            "id": eid,
            "ts": _now_iso(),
            "task_id": task_id,
            "type": event_type,
            "phase": phase,
            "page": page,
            "delta_tweets": int(delta_tweets),
            "delta_replies": int(delta_replies),
            "status": status,
            "risk_state": risk_state,
            "meta": meta or {},
        }
        state["events"].append(event)
        state["latest_action"] = event
        return deepcopy(event)


def _rate_per_min(deltas: deque, now_mono: float, window_sec: int) -> float:
    cutoff = now_mono - window_sec
    total = 0
    for ts, delta in deltas:
        if ts >= cutoff:
            total += delta
    if window_sec <= 0:
        return 0.0
    return round((total * 60.0) / float(window_sec), 2)


def get_snapshot(task_id: Optional[str], *, queue_position: Optional[int] = None) -> dict:
    if not task_id:
        return {
            "tweets_per_min_15s": 0.0,
            "tweets_per_min_60s": 0.0,
            "replies_per_min_15s": 0.0,
            "replies_per_min_60s": 0.0,
            "elapsed_sec": 0,
            "idle_sec": 0,
            "events_total": 0,
            "last_event_id": 0,
            "queue_position": queue_position,
        }

    now_mono = time.monotonic()
    with _lock:
        state = _ensure(task_id)
        _compact_rate_queue(state["tweet_deltas"], now_mono)
        _compact_rate_queue(state["reply_deltas"], now_mono)

        elapsed = max(0, int(now_mono - state["created_mono"]))
        idle = max(0, int(now_mono - state["last_mono"]))

        return {
            "tweets_per_min_15s": _rate_per_min(state["tweet_deltas"], now_mono, _RATE_WINDOWS[0]),
            "tweets_per_min_60s": _rate_per_min(state["tweet_deltas"], now_mono, _RATE_WINDOWS[1]),
            "replies_per_min_15s": _rate_per_min(state["reply_deltas"], now_mono, _RATE_WINDOWS[0]),
            "replies_per_min_60s": _rate_per_min(state["reply_deltas"], now_mono, _RATE_WINDOWS[1]),
            "elapsed_sec": elapsed,
            "idle_sec": idle,
            "events_total": len(state["events"]),
            "last_event_id": state["cursor"],
            "queue_position": queue_position,
        }


def get_latest_action(task_id: Optional[str]) -> Optional[dict]:
    if not task_id:
        return None
    with _lock:
        state = _store.get(task_id)
        if not state or not state.get("latest_action"):
            return None
        return deepcopy(state["latest_action"])


def get_events_since(task_id: Optional[str], *, after_id: int = 0, limit: int = 120) -> list[dict]:
    if not task_id:
        return []
    with _lock:
        state = _store.get(task_id)
        if not state:
            return []
        events = [e for e in state["events"] if int(e.get("id", 0)) > int(after_id)]
        if limit > 0:
            events = events[-limit:]
        return deepcopy(events)
