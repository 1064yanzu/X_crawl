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


def test_resume_all_resumes_standalone_and_queue_tasks_once(monkeypatch):
    from api.routers import tasks as tasks_router

    all_tasks = [
        {"task_id": "queue-1-a", "status": "paused", "queue_id": "queue-1"},
        {"task_id": "queue-1-b", "status": "stopped", "queue_id": "queue-1"},
        {"task_id": "solo-paused", "status": "paused"},
        {"task_id": "solo-stopped", "status": "stopped"},
        {"task_id": "running-task", "status": "running"},
        {"task_id": "done-task", "status": "done"},
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
    assert result["resumed"] == ["queue-1-a", "queue-1-b", "solo-paused", "solo-stopped"]
    assert result["already_running"] == ["running-task"]
    assert result["skipped"] == ["done-task"]
    assert result["failed"] == []


def test_resume_all_marks_all_queue_tasks_failed_when_queue_resume_errors(monkeypatch):
    from api.routers import tasks as tasks_router

    all_tasks = [
        {"task_id": "queue-1-a", "status": "paused", "queue_id": "queue-1"},
        {"task_id": "queue-1-b", "status": "failed", "queue_id": "queue-1"},
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
