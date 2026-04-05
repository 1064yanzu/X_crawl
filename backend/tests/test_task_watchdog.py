from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

from api.services import task_manager, task_watchdog
from config import settings


def test_watchdog_heals_stale_comment_backfill(monkeypatch):
    task_id = "stale-comment-task"
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat()
    stale_task = {
        "task_id": task_id,
        "task_kind": "comment_backfill",
        "status": "running",
        "queue_id": "queue-001",
        "keyword": "X 评论补采 · Generative AI",
        "created_at": stale_time,
        "last_event_at": stale_time,
    }

    monkeypatch.setattr(settings, "crawler_active_task_watchdog_enabled", True, raising=False)
    monkeypatch.setattr(settings, "crawler_active_task_stale_timeout_sec", 600.0, raising=False)
    monkeypatch.setattr(settings, "crawler_active_task_watchdog_interval_sec", 5.0, raising=False)
    monkeypatch.setattr(task_manager, "_tasks", {task_id: stale_task}, raising=False)
    monkeypatch.setattr(task_manager, "_tasks_lock", nullcontext(), raising=False)

    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(task_manager, "_get_task_summary_snapshot", lambda tid: dict(stale_task) if tid == task_id else None)
    monkeypatch.setattr(task_manager, "is_thread_alive", lambda tid: tid == task_id)
    monkeypatch.setattr(task_manager, "send_signal", lambda tid, signal: calls.append(("signal", f"{tid}:{signal}")))
    monkeypatch.setattr(task_manager, "clear_thread", lambda tid: calls.append(("clear_thread", tid)))
    monkeypatch.setattr(task_manager, "_get_task_result_snapshot", lambda tid, load=False: [{"id": "tweet-1"}])
    monkeypatch.setattr(task_manager, "update_task_phase", lambda tid, phase: calls.append(("phase", phase)))
    monkeypatch.setattr(task_manager, "update_task_stopped", lambda tid, tweets: calls.append(("stopped", str(len(tweets)))))
    monkeypatch.setattr(task_manager, "resume_finished_task", lambda tid: calls.append(("resume", tid)) or True)

    from api.services import task_queue_manager
    from api.services.task_scheduler import scheduler

    monkeypatch.setattr(task_queue_manager, "resume_queue", lambda queue_id: calls.append(("resume_queue", queue_id)) or {})
    monkeypatch.setattr(scheduler, "mark_done", lambda tid: calls.append(("mark_done", tid)))

    task_watchdog.maybe_heal_stale_active_tasks(force=True)

    assert ("signal", f"{task_id}:stop") in calls
    assert ("clear_thread", task_id) in calls
    assert ("mark_done", task_id) in calls
    assert ("stopped", "1") in calls
    assert ("resume_queue", "queue-001") in calls
    assert ("resume", task_id) not in calls


def test_watchdog_ignores_fresh_or_non_backfill_tasks(monkeypatch):
    fresh_time = datetime.now(timezone.utc).isoformat()
    fresh_task = {
        "task_id": "fresh-comment-task",
        "task_kind": "comment_backfill",
        "status": "running",
        "queue_id": None,
        "keyword": "X 评论补采 · Fresh",
        "created_at": fresh_time,
        "last_event_at": fresh_time,
    }
    normal_task = {
        "task_id": "normal-search-task",
        "task_kind": "search",
        "status": "running",
        "queue_id": None,
        "keyword": "OpenAI",
        "created_at": fresh_time,
        "last_event_at": fresh_time,
    }

    monkeypatch.setattr(settings, "crawler_active_task_watchdog_enabled", True, raising=False)
    monkeypatch.setattr(settings, "crawler_active_task_stale_timeout_sec", 600.0, raising=False)
    monkeypatch.setattr(settings, "crawler_active_task_watchdog_interval_sec", 5.0, raising=False)
    monkeypatch.setattr(task_manager, "_tasks", {
        fresh_task["task_id"]: fresh_task,
        normal_task["task_id"]: normal_task,
    }, raising=False)
    monkeypatch.setattr(task_manager, "_tasks_lock", nullcontext(), raising=False)

    calls: list[str] = []
    monkeypatch.setattr(task_manager, "_get_task_summary_snapshot", lambda tid: None)
    monkeypatch.setattr(task_manager, "send_signal", lambda tid, signal: calls.append(f"{tid}:{signal}"))

    task_watchdog.maybe_heal_stale_active_tasks(force=True)

    assert calls == []
