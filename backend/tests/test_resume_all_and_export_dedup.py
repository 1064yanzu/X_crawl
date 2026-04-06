from __future__ import annotations

import asyncio
import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _row(row_id: str, *, text: str = "hello", parent_tweet_id: str = "", row_type: str = "原帖") -> dict:
    return {
        "platform": "x",
        "id": row_id,
        "text": text,
        "row_type": row_type,
        "parent_tweet_id": parent_tweet_id,
    }


def test_batch_export_deduplicate_single_mode_removes_cross_task_duplicates():
    from api.routers import batch_export

    tasks_data = [
        ({"task_id": "task-1", "keyword": "OpenAI"}, [_row("1"), _row("2", text="same")]),
        ({"task_id": "task-2", "keyword": "Anthropic"}, [_row("2", text="same"), _row("3")]),
    ]

    deduped, removed = batch_export._deduplicate_tasks_data(tasks_data, merge_mode="single")

    assert removed == 1
    assert [row["id"] for _task, rows in deduped for row in rows] == ["1", "2", "3"]


def test_batch_export_deduplicate_per_task_mode_only_dedups_inside_each_task():
    from api.routers import batch_export

    tasks_data = [
        ({"task_id": "task-1", "keyword": "OpenAI"}, [_row("1"), _row("1")]),
        ({"task_id": "task-2", "keyword": "Anthropic"}, [_row("1"), _row("2")]),
    ]

    deduped, removed = batch_export._deduplicate_tasks_data(tasks_data, merge_mode="per_task")

    assert removed == 1
    assert [row["id"] for _task, rows in deduped for row in rows] == ["1", "1", "2"]


def test_build_merged_csv_keeps_source_columns_after_dedup():
    from api.routers import batch_export

    tasks_data = [
        ({"task_id": "task-1", "keyword": "OpenAI"}, [_row("1")]),
        ({"task_id": "task-2", "keyword": "Anthropic"}, [_row("1"), _row("2")]),
    ]

    deduped, _removed = batch_export._deduplicate_tasks_data(tasks_data, merge_mode="single")
    data = batch_export._build_merged_csv(deduped)
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))

    assert len(rows) == 2
    assert rows[0]["来源任务ID"] == "task-1"
    assert rows[0]["来源关键词"] == "OpenAI"
    assert rows[1]["来源任务ID"] == "task-2"
    assert rows[1]["来源关键词"] == "Anthropic"


def test_collect_all_rows_tolerates_none_reply_to_and_fills_parent_author():
    from api.routers.export import _collect_all_rows

    tweets = [
        {
            "id": "tweet-1",
            "text": "post",
            "author": {"name": "Parent Author"},
            "replies": [
                {
                    "id": "reply-1",
                    "text": "reply",
                    "reply_to": None,
                    "author": {"name": "Reply Author"},
                }
            ],
        }
    ]

    rows = _collect_all_rows(tweets, "x")

    assert len(rows) == 2
    assert rows[1]["reply_to"]["screen_name"] == "Parent Author"
    assert rows[1]["parent_tweet_id"] == "tweet-1"


def test_batch_export_uses_lightweight_task_payload(monkeypatch):
    from api.routers import batch_export

    payload_calls: list[str] = []

    monkeypatch.setattr(
        batch_export.task_manager,
        "get_task_export_payload_readonly",
        lambda task_id: payload_calls.append(task_id) or {
            "task_id": task_id,
            "keyword": "kw",
            "platform": "x",
            "task_kind": "search",
            "fetch_replies": False,
            "replies_fetched": 0,
            "source_task_id": None,
            "source_task_ids": [],
            "tweets": [{"id": "1", "text": "hello"}],
        },
    )

    tasks_data = batch_export._get_tasks_data(["task-1", "task-2"])

    assert payload_calls == ["task-1", "task-2"]
    assert len(tasks_data) == 2


def test_export_hydrates_missing_x_replies_preferring_raw_then_richer_candidates(monkeypatch):
    from api.routers import export as export_router

    source_replies = [
        {"id": "reply-source", "text": "source reply"},
    ]
    cached_replies = [
        {"id": "reply-cache-1", "text": "cache reply 1"},
        {"id": "reply-cache-2", "text": "cache reply 2", "replies": [{"id": "nested-1", "text": "nested"}]},
    ]

    raw_replies = [
        {"id": "reply-raw-1", "text": "raw reply"},
        {"id": "reply-raw-2", "text": "raw reply 2"},
    ]

    monkeypatch.setattr(
        export_router.task_manager,
        "get_task_export_payload_readonly",
        lambda task_id: {
            "task_id": task_id,
            "platform": "x",
            "tweets": [{"id": "tweet-1", "replies": source_replies}],
        } if task_id == "source-1" else None,
    )
    monkeypatch.setattr(
        export_router.task_db,
        "load_cached_replies_map",
        lambda tweet_ids: {"tweet-1": cached_replies},
    )
    monkeypatch.setattr(
        export_router,
        "_load_raw_reply_map",
        lambda task_id, tweet_ids: {"tweet-1": raw_replies},
    )

    task = {
        "task_id": "backfill-1",
        "platform": "x",
        "task_kind": "comment_backfill",
        "fetch_replies": True,
        "replies_fetched": 10,
        "source_task_id": "source-1",
        "source_task_ids": [],
    }
    tweets = [{"id": "tweet-1", "text": "post", "replies": None}]

    hydrated = export_router._hydrate_tweets_for_export(task, tweets)

    assert hydrated[0]["replies"] == cached_replies


def test_get_export_estimate_uses_replies_fetched(monkeypatch):
    from api.services import task_manager

    summaries = {
        "task-1": {
            "task_id": "task-1",
            "keyword": "Claude",
            "result_count": 12,
            "replies_fetched": 34,
        }
    }

    monkeypatch.setattr(
        task_manager,
        "_get_task_summary_snapshot",
        lambda task_id: summaries.get(task_id),
    )
    monkeypatch.setattr(task_manager, "_ensure_db", lambda: None)

    result = task_manager.get_export_estimate(["task-1"])

    assert result["total_tweets"] == 12
    assert result["total_replies"] == 34
    assert result["total_rows"] == 46


def test_resume_all_resumes_standalone_and_queue_tasks_once(monkeypatch):
    from api.routers import tasks as tasks_router

    all_tasks = [
        {"task_id": "queue-1-a", "status": "paused", "queue_id": "queue-1", "risk_state": "none"},
        {"task_id": "queue-1-b", "status": "stopped", "queue_id": "queue-1", "risk_state": "none"},
        {"task_id": "solo-paused", "status": "paused", "risk_state": "none"},
        {"task_id": "solo-stopped", "status": "stopped", "risk_state": "none"},
        {"task_id": "running-task", "status": "running", "risk_state": "none"},
        {"task_id": "done-task", "status": "done", "risk_state": "none"},
    ]

    queue_calls: list[str] = []
    thread_starts: list[str] = []
    resume_calls: list[str] = []
    resume_finished_calls: list[str] = []

    monkeypatch.setattr(tasks_router.task_manager, "list_tasks", lambda include_payload=False: all_tasks)
    monkeypatch.setattr(
        tasks_router.task_queue_manager,
        "resume_queue",
        lambda queue_id: queue_calls.append(queue_id) or {
            "resumed": ["queue-1-a", "queue-1-b"],
            "already_running": [],
            "skipped": [],
        },
    )
    monkeypatch.setattr(tasks_router.task_manager, "resume_task", lambda task_id: resume_calls.append(task_id) or True)
    monkeypatch.setattr(tasks_router.task_manager, "is_thread_alive", lambda task_id: task_id == "solo-paused")
    monkeypatch.setattr(
        tasks_router.task_manager,
        "resume_finished_task",
        lambda task_id: resume_finished_calls.append(task_id) or True,
    )
    monkeypatch.setattr(
        tasks_router.crawl_service,
        "start_crawler_thread",
        lambda task_id, task, force_new_browser=False: thread_starts.append(task_id),
    )

    result = asyncio.run(tasks_router.resume_all_tasks())

    assert queue_calls == ["queue-1"]
    assert resume_calls == ["solo-paused"]
    assert resume_finished_calls == ["solo-stopped"]
    assert thread_starts == ["solo-stopped"]
    assert result["scenario"] == "user_paused"
    assert result["resumed"] == ["queue-1-a", "queue-1-b", "solo-paused", "solo-stopped"]
    # done 任务不在 target 中，属于 skipped；running 任务被排除在 skipped 计算外
    assert "done-task" in result["skipped"]
    assert "running-task" not in result["skipped"]
    assert result["failed"] == []


def test_resume_all_marks_all_queue_tasks_failed_when_queue_resume_errors(monkeypatch):
    from api.routers import tasks as tasks_router

    all_tasks = [
        {"task_id": "queue-1-a", "status": "paused", "queue_id": "queue-1", "risk_state": "none"},
        {"task_id": "queue-1-b", "status": "failed", "queue_id": "queue-1", "risk_state": "none"},
    ]

    monkeypatch.setattr(tasks_router.task_manager, "list_tasks", lambda include_payload=False: all_tasks)
    monkeypatch.setattr(
        tasks_router.task_queue_manager,
        "resume_queue",
        lambda queue_id: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = asyncio.run(tasks_router.resume_all_tasks())

    assert result["resumed"] == []
    assert result["already_running"] == []
    assert result["skipped"] == []
    assert result["failed"] == ["queue-1-a", "queue-1-b"]


# ── pause-all ──────────────────────────────────────────────────────────

def test_pause_all_pauses_running_and_pending_tasks(monkeypatch):
    from api.routers import tasks as tasks_router

    all_tasks = [
        {"task_id": "running-1", "status": "running"},
        {"task_id": "running-2", "status": "running"},
        {"task_id": "pending-1", "status": "pending"},
        {"task_id": "done-1", "status": "done"},
        {"task_id": "paused-1", "status": "paused"},
    ]

    paused_calls: list[str] = []
    stopped_calls: list[str] = []
    mark_paused_calls: list[str] = []

    monkeypatch.setattr(tasks_router.task_manager, "list_tasks", lambda include_payload=False: all_tasks)
    monkeypatch.setattr(
        tasks_router.task_manager, "pause_task",
        lambda task_id: paused_calls.append(task_id) or True,
    )
    monkeypatch.setattr(
        tasks_router.task_manager, "stop_task",
        lambda task_id: stopped_calls.append(task_id) or True,
    )
    monkeypatch.setattr(
        tasks_router.task_queue_manager, "mark_task_paused",
        lambda task_id: mark_paused_calls.append(task_id),
    )

    result = asyncio.run(tasks_router.pause_all_tasks())

    assert paused_calls == ["running-1", "running-2"]
    assert stopped_calls == ["pending-1"]
    assert mark_paused_calls == ["running-1", "running-2"]
    assert result["paused"] == ["running-1", "running-2"]
    assert result["stopped"] == ["pending-1"]
    assert "done-1" in result["skipped"]
    assert "paused-1" in result["skipped"]
    assert result["failed"] == []


def test_pause_all_skips_non_active_tasks(monkeypatch):
    from api.routers import tasks as tasks_router

    all_tasks = [
        {"task_id": "done-1", "status": "done"},
        {"task_id": "failed-1", "status": "failed"},
        {"task_id": "stopped-1", "status": "stopped"},
    ]

    monkeypatch.setattr(tasks_router.task_manager, "list_tasks", lambda include_payload=False: all_tasks)

    result = asyncio.run(tasks_router.pause_all_tasks())

    assert result["paused"] == []
    assert result["stopped"] == []
    assert len(result["skipped"]) == 3
    assert result["failed"] == []


# ── classify_resumable_tasks ──────────────────────────────────────────

def test_classify_user_paused_vs_risk_paused():
    from api.routers.tasks import _classify_resumable_tasks

    all_tasks = [
        {"task_id": "user-paused", "status": "paused", "risk_state": "none"},
        {"task_id": "user-stopped", "status": "stopped", "risk_state": "none", "quality_state": "interrupted"},
        {"task_id": "risk-paused", "status": "paused", "risk_state": "challenge"},
        {"task_id": "risk-failed", "status": "failed", "risk_state": "rate_limited"},
        {"task_id": "normal-failed", "status": "failed", "risk_state": "none"},
        {"task_id": "running-1", "status": "running", "risk_state": "none"},
        {"task_id": "done-1", "status": "done", "risk_state": "none"},
    ]

    user_paused, risk_paused = _classify_resumable_tasks(all_tasks)

    user_ids = {t["task_id"] for t in user_paused}
    risk_ids = {t["task_id"] for t in risk_paused}

    assert user_ids == {"user-paused", "user-stopped", "normal-failed"}
    assert risk_ids == {"risk-paused", "risk-failed"}


# ── smart resume-all scenarios ────────────────────────────────────────

def _setup_resume_mocks(monkeypatch, tasks_router, all_tasks):
    """Common mock setup for resume-all tests."""
    resume_calls: list[str] = []
    resume_finished_calls: list[str] = []
    thread_starts: list[str] = []

    monkeypatch.setattr(tasks_router.task_manager, "list_tasks", lambda include_payload=False: all_tasks)
    monkeypatch.setattr(tasks_router.task_manager, "resume_task", lambda task_id: resume_calls.append(task_id) or True)
    monkeypatch.setattr(tasks_router.task_manager, "is_thread_alive", lambda task_id: False)
    monkeypatch.setattr(
        tasks_router.task_manager, "resume_finished_task",
        lambda task_id: resume_finished_calls.append(task_id) or True,
    )
    monkeypatch.setattr(
        tasks_router.crawl_service, "start_crawler_thread",
        lambda task_id, task, force_new_browser=False: thread_starts.append(task_id),
    )
    monkeypatch.setattr(
        tasks_router.task_queue_manager, "resume_queue",
        lambda queue_id: {"resumed": [], "already_running": [], "skipped": []},
    )

    return resume_calls, resume_finished_calls, thread_starts


def test_resume_all_scenario_user_paused_only(monkeypatch):
    from api.routers import tasks as tasks_router

    all_tasks = [
        {"task_id": "user-paused", "status": "paused", "risk_state": "none"},
        {"task_id": "user-stopped", "status": "stopped", "risk_state": "none"},
        {"task_id": "done-1", "status": "done", "risk_state": "none"},
    ]

    resume_calls, resume_finished_calls, thread_starts = _setup_resume_mocks(monkeypatch, tasks_router, all_tasks)

    result = asyncio.run(tasks_router.resume_all_tasks())

    assert result["scenario"] == "user_paused"
    assert "user-paused" in result["resumed"]
    assert "user-stopped" in result["resumed"]
    # done-1 should be skipped (not in target set)
    assert "done-1" in result["skipped"]


def test_resume_all_scenario_risk_only(monkeypatch):
    from api.routers import tasks as tasks_router

    all_tasks = [
        {"task_id": "risk-paused", "status": "paused", "risk_state": "challenge"},
        {"task_id": "risk-failed", "status": "failed", "risk_state": "rate_limited"},
        {"task_id": "done-1", "status": "done", "risk_state": "none"},
    ]

    resume_calls, resume_finished_calls, thread_starts = _setup_resume_mocks(monkeypatch, tasks_router, all_tasks)

    result = asyncio.run(tasks_router.resume_all_tasks())

    assert result["scenario"] == "risk_control"
    assert "risk-paused" in result["resumed"]
    assert "risk-failed" in result["resumed"]


def test_resume_all_scenario_mixed(monkeypatch):
    from api.routers import tasks as tasks_router

    all_tasks = [
        {"task_id": "user-paused", "status": "paused", "risk_state": "none"},
        {"task_id": "risk-paused", "status": "paused", "risk_state": "challenge"},
        {"task_id": "running-1", "status": "running", "risk_state": "none"},
    ]

    resume_calls, resume_finished_calls, thread_starts = _setup_resume_mocks(monkeypatch, tasks_router, all_tasks)

    result = asyncio.run(tasks_router.resume_all_tasks())

    assert result["scenario"] == "mixed"
    assert "user-paused" in result["resumed"]
    assert "risk-paused" in result["resumed"]


def test_resume_all_scenario_none(monkeypatch):
    from api.routers import tasks as tasks_router

    all_tasks = [
        {"task_id": "running-1", "status": "running", "risk_state": "none"},
        {"task_id": "done-1", "status": "done", "risk_state": "none"},
    ]

    monkeypatch.setattr(tasks_router.task_manager, "list_tasks", lambda include_payload=False: all_tasks)

    result = asyncio.run(tasks_router.resume_all_tasks())

    assert result["scenario"] == "none"
    assert result["resumed"] == []
