from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def queue_modules(tmp_path):
    import config
    from api.services import task_db, task_manager, task_queue_manager

    config.settings.tasks_db_path = str(tmp_path / "queue.db")
    db_module = importlib.reload(task_db)
    manager = importlib.reload(task_manager)
    queue_manager = importlib.reload(task_queue_manager)
    yield manager, queue_manager, db_module

    conn = getattr(db_module._local, "conn", None)
    if conn is not None:
        conn.close()
        db_module._local.conn = None


def test_create_queue_only_starts_first_task(queue_modules, monkeypatch):
    manager, queue_manager, _db_module = queue_modules
    from api.services import crawl_service

    started: list[str] = []

    monkeypatch.setattr(
        crawl_service,
        "start_crawler_thread",
        lambda task_id, task, force_new_browser=False, resume=True: started.append(task_id),
    )

    queue = queue_manager.create_queue(
        name="品牌监测批次",
        task_payloads=[
            {"keyword": "OpenAI", "max_count": 10, "product": "Latest", "platform": "x"},
            {"keyword": "Anthropic", "max_count": 20, "product": "Top", "platform": "x"},
        ],
    )

    assert queue["name"] == "品牌监测批次"
    assert queue["total_tasks"] == 2
    assert len(started) == 1
    assert started[0] == queue["tasks"][0]["task_id"]

    second_task = manager.get_task_summary(queue["tasks"][1]["task_id"])
    assert second_task is not None
    assert second_task["queue_name"] == "品牌监测批次"
    assert second_task["queue_order"] == 2
    assert second_task["queue_total"] == 2
    assert "等待前序任务完成" in second_task["crawl_phase"]


def test_queue_advances_to_next_task_after_terminal(queue_modules, monkeypatch):
    manager, queue_manager, _db_module = queue_modules
    from api.services import crawl_service

    started: list[str] = []

    monkeypatch.setattr(
        crawl_service,
        "start_crawler_thread",
        lambda task_id, task, force_new_browser=False, resume=True: started.append(task_id),
    )

    queue = queue_manager.create_queue(
        name="顺序批次",
        task_payloads=[
            {"keyword": "A", "max_count": 10, "product": "Latest", "platform": "x"},
            {"keyword": "B", "max_count": 10, "product": "Latest", "platform": "x"},
        ],
    )

    first_task_id = queue["tasks"][0]["task_id"]
    second_task_id = queue["tasks"][1]["task_id"]

    can_resume, reason, needs_queue = queue_manager.can_resume_task(second_task_id)
    assert can_resume is True
    assert needs_queue is True

    manager.update_task_result(first_task_id, tweets=[], runtime_metrics={})
    queue_manager.notify_task_terminal(first_task_id, "done")

    assert started[-1] == second_task_id
    refreshed = queue_manager.get_queue(queue["queue_id"])
    assert refreshed is not None
    assert refreshed["current_task_id"] == second_task_id
    assert refreshed["status"] == "running"


def test_create_comment_backfill_queue_preserves_seed_tweets(queue_modules, monkeypatch):
    manager, queue_manager, _db_module = queue_modules
    from api.services import crawl_service

    started: list[str] = []

    monkeypatch.setattr(
        crawl_service,
        "start_crawler_thread",
        lambda task_id, task, force_new_browser=False, resume=True: started.append(task_id),
    )

    seed_tweets = [
        {
            "id": "1001",
            "text": "hello",
            "url": "https://x.com/openai/status/1001",
            "author": {"screen_name": "openai", "name": "OpenAI"},
            "metrics": {"replies": 8},
        }
    ]
    queue = queue_manager.create_queue(
        name="评论补采批次",
        task_payloads=[
            {
                "keyword": "X 评论补采 · OpenAI",
                "max_count": 1,
                "product": "Comments",
                "platform": "x",
                "task_kind": "comment_backfill",
                "source_task_id": "source-task-1",
                "comment_backfill_progress": {
                    "total_posts": 1,
                    "eligible_posts": 1,
                },
                "seed_tweets": seed_tweets,
            },
            {
                "keyword": "X 评论补采 · Anthropic",
                "max_count": 1,
                "product": "Comments",
                "platform": "x",
                "task_kind": "comment_backfill",
                "source_task_id": "source-task-2",
                "comment_backfill_progress": {
                    "total_posts": 1,
                    "eligible_posts": 1,
                },
                "seed_tweets": seed_tweets,
            },
        ],
    )

    first_task_id = queue["tasks"][0]["task_id"]
    second_task_id = queue["tasks"][1]["task_id"]
    first_full = manager.get_task_full(first_task_id)
    second_full = manager.get_task_full(second_task_id)

    assert started == [first_task_id]
    assert first_full is not None
    assert first_full["task_kind"] == "comment_backfill"
    assert first_full["source_task_id"] == "source-task-1"
    assert first_full["result_count"] == 1
    assert first_full["tweets"][0]["id"] == "1001"
    assert second_full is not None
    assert second_full["source_task_id"] == "source-task-2"
    assert second_full["result_count"] == 1
    assert second_full["tweets"][0]["id"] == "1001"
