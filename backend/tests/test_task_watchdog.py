from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

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
    monkeypatch.setattr(settings, "crawler_search_stall_timeout_sec", 600.0, raising=False)
    monkeypatch.setattr(settings, "crawler_search_stall_warn_sec", 300.0, raising=False)
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
    monkeypatch.setattr(settings, "crawler_search_stall_timeout_sec", 600.0, raising=False)
    monkeypatch.setattr(settings, "crawler_search_stall_warn_sec", 300.0, raising=False)
    monkeypatch.setattr(task_manager, "_tasks", {
        fresh_task["task_id"]: fresh_task,
        normal_task["task_id"]: normal_task,
    }, raising=False)
    monkeypatch.setattr(task_manager, "_tasks_lock", nullcontext(), raising=False)

    calls: list[str] = []
    monkeypatch.setattr(task_manager, "_get_task_summary_snapshot", lambda tid: None)
    monkeypatch.setattr(task_manager, "send_signal", lambda tid, signal: calls.append(f"{tid}:{signal}"))

    # 让 telemetry 返回 idle_sec=0 （新任务，没有卡住）
    mock_telemetry = MagicMock()
    mock_telemetry.get_snapshot.return_value = {"idle_sec": 0}
    with patch("api.services.task_watchdog.telemetry", mock_telemetry, create=True):
        # 直接测 _check_search_task_stall，传入假 task_manager
        pass

    task_watchdog.maybe_heal_stale_active_tasks(force=True)

    assert calls == []


def test_watchdog_warns_on_stalling_search_task(monkeypatch):
    """搜索任务空闲超过 warn_sec 时，watchdog 应发出警告并更新 phase，但不自愈。"""
    task_id = "stalling-search-task"
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=7)).isoformat()
    stall_task = {
        "task_id": task_id,
        "task_kind": "search",
        "status": "running",
        "queue_id": None,
        "keyword": "大模型",
        "platform": "weibo",
        "created_at": stale_time,
        "last_event_at": stale_time,
    }

    monkeypatch.setattr(settings, "crawler_active_task_watchdog_enabled", True, raising=False)
    monkeypatch.setattr(settings, "crawler_active_task_watchdog_interval_sec", 5.0, raising=False)
    monkeypatch.setattr(settings, "crawler_search_stall_warn_sec", 60.0, raising=False)   # 1 分钟警告
    monkeypatch.setattr(settings, "crawler_search_stall_timeout_sec", 600.0, raising=False)  # 10 分钟自愈
    monkeypatch.setattr(settings, "crawler_active_task_stale_timeout_sec", 900.0, raising=False)
    monkeypatch.setattr(task_manager, "_tasks", {task_id: stall_task}, raising=False)
    monkeypatch.setattr(task_manager, "_tasks_lock", nullcontext(), raising=False)

    phase_updates: list[str] = []
    heal_calls: list[str] = []

    monkeypatch.setattr(task_manager, "update_task_phase", lambda tid, phase: phase_updates.append(phase))
    monkeypatch.setattr(task_manager, "send_signal", lambda tid, signal: heal_calls.append(f"{tid}:{signal}"))
    monkeypatch.setattr(task_manager, "_get_task_summary_snapshot", lambda tid: dict(stall_task) if tid == task_id else None)
    monkeypatch.setattr(task_manager, "is_thread_alive", lambda tid: True)

    # telemetry 返回较长 idle（7 分钟 = 420 秒）
    mock_snap = MagicMock()
    mock_snap.return_value = {"idle_sec": 420}

    with patch("api.services.task_watchdog._get_search_task_idle_sec", return_value=420.0):
        # 清除冷却缓存，确保本次调用能触发警告
        task_watchdog._search_warn_cooldown.clear()
        task_watchdog._search_heal_cooldown.clear()
        task_watchdog.maybe_heal_stale_active_tasks(force=True)

    # 应该有 phase 警告，但不应触发 stop 信号（因为 420s < 600s 自愈阈值）
    assert any("watchdog" in p or "分钟" in p for p in phase_updates), \
        f"期望 phase 包含警告信息，实际: {phase_updates}"
    assert not any("stop" in c for c in heal_calls), \
        f"不应发送 stop 信号（仅警告阶段），实际: {heal_calls}"


def test_watchdog_heals_stuck_search_task(monkeypatch):
    """搜索任务空闲超过 stall_timeout_sec 时，watchdog 应执行自愈重启。"""
    task_id = "stuck-search-task"
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    stuck_task = {
        "task_id": task_id,
        "task_kind": "search",
        "status": "running",
        "queue_id": None,
        "keyword": "人工智能",
        "product": "Top",
        "platform": "weibo",
        "created_at": stale_time,
        "last_event_at": stale_time,
    }

    monkeypatch.setattr(settings, "crawler_active_task_watchdog_enabled", True, raising=False)
    monkeypatch.setattr(settings, "crawler_active_task_watchdog_interval_sec", 5.0, raising=False)
    monkeypatch.setattr(settings, "crawler_search_stall_warn_sec", 60.0, raising=False)    # 1 分钟警告
    monkeypatch.setattr(settings, "crawler_search_stall_timeout_sec", 300.0, raising=False) # 5 分钟自愈
    monkeypatch.setattr(settings, "crawler_active_task_stale_timeout_sec", 900.0, raising=False)
    monkeypatch.setattr(task_manager, "_tasks", {task_id: stuck_task}, raising=False)
    monkeypatch.setattr(task_manager, "_tasks_lock", nullcontext(), raising=False)

    calls: list[tuple] = []

    monkeypatch.setattr(task_manager, "_get_task_summary_snapshot", lambda tid: dict(stuck_task) if tid == task_id else None)
    monkeypatch.setattr(task_manager, "is_thread_alive", lambda tid: True)
    monkeypatch.setattr(task_manager, "send_signal", lambda tid, signal: calls.append(("signal", f"{tid}:{signal}")))
    monkeypatch.setattr(task_manager, "clear_thread", lambda tid: calls.append(("clear_thread", tid)))
    monkeypatch.setattr(task_manager, "_get_task_result_snapshot", lambda tid, load=False: [{"id": "post-1"}, {"id": "post-2"}])
    monkeypatch.setattr(task_manager, "update_task_phase", lambda tid, phase: calls.append(("phase", phase)))
    monkeypatch.setattr(task_manager, "update_task_stopped", lambda tid, tweets: calls.append(("stopped", str(len(tweets)))))
    monkeypatch.setattr(task_manager, "resume_finished_task", lambda tid: calls.append(("resume", tid)) or True)

    from api.services import task_queue_manager
    from api.services.task_scheduler import scheduler

    monkeypatch.setattr(task_queue_manager, "resume_queue", lambda queue_id: calls.append(("resume_queue", queue_id)) or {})
    monkeypatch.setattr(scheduler, "mark_done", lambda tid: calls.append(("mark_done", tid)))

    # idle = 1200 秒（20 分钟），远超 300 秒自愈阈值
    with patch("api.services.task_watchdog._get_search_task_idle_sec", return_value=1200.0):
        task_watchdog._search_warn_cooldown.clear()
        task_watchdog._search_heal_cooldown.clear()
        task_watchdog.maybe_heal_stale_active_tasks(force=True)

    # 应触发 stop 信号和重排
    assert ("signal", f"{task_id}:stop") in calls, f"期望发送 stop 信号，实际: {calls}"
    assert ("clear_thread", task_id) in calls, f"期望清理线程，实际: {calls}"
    assert ("mark_done", task_id) in calls, f"期望 mark_done，实际: {calls}"
    assert ("stopped", "2") in calls, f"期望保存已有数据，实际: {calls}"
    # 无 queue_id，走 resume_finished_task 路径
    assert ("resume", task_id) in calls, f"期望 resume 任务，实际: {calls}"


def test_watchdog_search_task_heal_cooldown(monkeypatch):
    """同一 search 任务短时间内不应被重复自愈（冷却机制）。"""
    import time

    task_id = "cooldown-search-task"
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    stuck_task = {
        "task_id": task_id,
        "task_kind": "search",
        "status": "running",
        "queue_id": None,
        "keyword": "ChatGPT",
        "product": "Top",
        "platform": "x",
        "created_at": stale_time,
        "last_event_at": stale_time,
    }

    monkeypatch.setattr(settings, "crawler_active_task_watchdog_enabled", True, raising=False)
    monkeypatch.setattr(settings, "crawler_active_task_watchdog_interval_sec", 5.0, raising=False)
    monkeypatch.setattr(settings, "crawler_search_stall_warn_sec", 60.0, raising=False)
    monkeypatch.setattr(settings, "crawler_search_stall_timeout_sec", 300.0, raising=False)
    monkeypatch.setattr(settings, "crawler_active_task_stale_timeout_sec", 900.0, raising=False)
    monkeypatch.setattr(task_manager, "_tasks", {task_id: stuck_task}, raising=False)
    monkeypatch.setattr(task_manager, "_tasks_lock", nullcontext(), raising=False)

    stop_signal_count = [0]

    monkeypatch.setattr(task_manager, "_get_task_summary_snapshot", lambda tid: dict(stuck_task) if tid == task_id else None)
    monkeypatch.setattr(task_manager, "is_thread_alive", lambda tid: True)
    monkeypatch.setattr(task_manager, "send_signal", lambda tid, signal: stop_signal_count.__setitem__(0, stop_signal_count[0] + 1) if signal == "stop" else None)
    monkeypatch.setattr(task_manager, "clear_thread", lambda tid: None)
    monkeypatch.setattr(task_manager, "_get_task_result_snapshot", lambda tid, load=False: [])
    monkeypatch.setattr(task_manager, "update_task_phase", lambda tid, phase: None)
    monkeypatch.setattr(task_manager, "update_task_stopped", lambda tid, tweets: None)
    monkeypatch.setattr(task_manager, "resume_finished_task", lambda tid: True)

    from api.services.task_scheduler import scheduler
    monkeypatch.setattr(scheduler, "mark_done", lambda tid: None)

    with patch("api.services.task_watchdog._get_search_task_idle_sec", return_value=1200.0):
        task_watchdog._search_warn_cooldown.clear()
        task_watchdog._search_heal_cooldown.clear()

        # 第一次自愈
        task_watchdog.maybe_heal_stale_active_tasks(force=True)
        first_count = stop_signal_count[0]

        # 立即再次触发（冷却期内），不应再次自愈
        task_watchdog.maybe_heal_stale_active_tasks(force=True)
        second_count = stop_signal_count[0]

    assert first_count == 1, f"第一次应触发 1 次 stop，实际: {first_count}"
    assert second_count == 1, f"冷却期内不应再触发 stop，实际: {second_count}"
