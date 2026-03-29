from __future__ import annotations

import asyncio
import importlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _base_task(task_id: str = "task-1") -> dict:
    return {
        "task_id": task_id,
        "status": "done",
        "keyword": "hello",
        "product": "Top",
        "max_count": 100,
        "result_count": 2,
        "current_page": 3,
        "created_at": "2026-03-10T00:00:00+00:00",
        "finished_at": "2026-03-10T00:10:00+00:00",
        "error": None,
        "risk_state": "none",
        "quality_state": "complete",
        "runtime_metrics": {},
        "time_coverage": {},
        "last_event_at": "2026-03-10T00:10:00+00:00",
        "resumed": False,
        "fetch_replies": False,
        "max_replies_per_tweet": 0,
        "crawl_strategy": "dfs",
        "replies_fetched": 1,
        "crawl_phase": "done",
        "segment_progress": {},
        "preview_tweets": [{"id": "2", "text": "preview"}],
        "tweets": [
            {"id": "1", "text": "first", "created_at": "2026-03-09T00:00:00+00:00"},
            {
                "id": "2",
                "text": "second",
                "created_at": "2026-03-10T00:00:00+00:00",
                "replies": [{"id": "r1", "created_at": "2026-03-10T01:00:00+00:00"}],
            },
        ],
        "task_kind": "search",
        "source_file_name": None,
        "source_task_id": None,
        "platform": "x",
        "start_date": None,
        "end_date": None,
    }


@pytest.fixture()
def task_db_module(tmp_path):
    from api.services import task_db

    module = importlib.reload(task_db)
    db_path = tmp_path / "tasks.db"
    module.init_db(db_path)
    yield module, db_path

    conn = getattr(module._local, "conn", None)
    if conn is not None:
        conn.close()
        module._local.conn = None


@pytest.fixture()
def task_manager_module(tmp_path):
    import config
    from api.services import task_db, task_manager

    config.settings.tasks_db_path = str(tmp_path / "manager.db")
    task_db_module = importlib.reload(task_db)
    manager = importlib.reload(task_manager)
    yield manager

    conn = getattr(task_db_module._local, "conn", None)
    if conn is not None:
        conn.close()
        task_db_module._local.conn = None


def test_task_db_keeps_summary_and_full_result_separate(task_db_module):
    task_db, db_path = task_db_module
    task = _base_task()

    task_db.save_task(task)

    summaries = task_db.load_all_tasks()
    assert len(summaries) == 1
    assert summaries[0]["tweets"] == []
    assert summaries[0]["preview_tweets"] == task["preview_tweets"]

    assert task_db.load_task_result(task["task_id"]) == task["tweets"]

    updated = {**task, "preview_tweets": [{"id": "p"}], "tweets": []}
    task_db.save_task_summary(updated)
    assert task_db.load_task_result(task["task_id"]) == task["tweets"]

    with sqlite3.connect(db_path) as conn:
        result_row = conn.execute(
            "SELECT tweets_json FROM task_results WHERE task_id = ?",
            (task["task_id"],),
        ).fetchone()
    assert json.loads(result_row[0]) == task["tweets"]


def test_task_db_persists_source_task_id_in_summary(task_db_module):
    task_db, _db_path = task_db_module
    task = {**_base_task("source-linked-task"), "task_kind": "comment_backfill", "source_task_id": "origin-001"}

    task_db.save_task(task)

    summaries = task_db.load_all_tasks()
    assert len(summaries) == 1
    assert summaries[0]["task_kind"] == "comment_backfill"
    assert summaries[0]["source_task_id"] == "origin-001"


def test_task_db_persists_recrawl_flags_in_summary(task_db_module):
    task_db, _db_path = task_db_module
    task = {
        **_base_task("recrawl-task"),
        "source_task_id": "origin-002",
        "is_recrawl": True,
        "exclude_count": 42,
    }

    task_db.save_task(task)

    summaries = task_db.load_all_tasks()
    assert len(summaries) == 1
    assert summaries[0]["is_recrawl"] is True
    assert summaries[0]["exclude_count"] == 42


def test_task_db_lazy_migrates_legacy_tweets_json(task_db_module):
    task_db, db_path = task_db_module
    task = _base_task("legacy-task")
    task_db.save_task_summary(task)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET tweets_json = ? WHERE task_id = ?",
            (json.dumps(task["tweets"], ensure_ascii=False), task["task_id"]),
        )
        conn.commit()

    assert task_db.load_task_result(task["task_id"]) == task["tweets"]

    with sqlite3.connect(db_path) as conn:
        migrated = conn.execute(
            "SELECT tweets_json FROM task_results WHERE task_id = ?",
            (task["task_id"],),
        ).fetchone()
    assert json.loads(migrated[0]) == task["tweets"]


def test_task_manager_summary_and_full_views_split_payload(task_manager_module):
    manager = task_manager_module
    task_id = manager.create_task("hello", 100, "Top")
    tweets = _base_task(task_id)["tweets"]

    manager.update_task_progress(task_id, current_page=1, tweets_so_far=tweets)

    summary = manager.get_task_summary(task_id)
    full = manager.get_task_full(task_id)
    listed_summary = manager.list_tasks(include_payload=False)
    listed_full = manager.list_tasks(include_payload=True)

    assert summary is not None and summary["tweets"] == []
    assert full is not None and full["tweets"] == tweets
    assert listed_summary[0]["tweets"] == []
    assert listed_full[0]["tweets"] == tweets


def test_task_manager_set_task_seed_tweets_persists_full_result(task_manager_module):
    manager = task_manager_module
    task_id = manager.create_task(
        "微博 评论补采 · OpenAI",
        1,
        "Comments",
        task_kind="comment_backfill",
        source_task_id="source-task-001",
    )
    tweets = [
        {
            "id": "1001",
            "text": "seed",
            "url": "https://weibo.com/detail/1001",
            "author": {"id": "u-1", "screen_name": "openai", "name": "OpenAI"},
            "metrics": {"replies": 6},
        }
    ]

    manager.set_task_seed_tweets(task_id, tweets, current_page=0)

    summary = manager.get_task_summary(task_id)
    full = manager.get_task_full(task_id)

    assert summary is not None
    assert summary["source_task_id"] == "source-task-001"
    assert summary["result_count"] == 1
    assert full is not None
    assert full["tweets"] == tweets


def test_task_manager_can_rebuild_recrawl_exclude_ids_from_source_task(task_manager_module):
    manager = task_manager_module
    source_task_id = manager.create_task("source", 100, "Top")
    manager.set_task_seed_tweets(
        source_task_id,
        [
            {"id": "1", "text": "one"},
            {"id": "2", "text": "two"},
            {"mid": "3", "text": "three"},
        ],
        current_page=0,
    )

    recrawl_task_id = manager.create_task(
        "source",
        100,
        "Top",
        source_task_id=source_task_id,
        is_recrawl=True,
    )

    exclude_ids = manager.ensure_task_exclude_tweet_ids(recrawl_task_id)
    summary = manager.get_task_summary(recrawl_task_id)

    assert exclude_ids == ["1", "2", "3"]
    assert summary is not None
    assert summary["is_recrawl"] is True
    assert summary["exclude_count"] == 3


def test_search_route_uses_summary_path_for_lightweight_polling(monkeypatch):
    from api.routers import search

    task = {
        "task_id": "route-task",
        "status": "running",
        "keyword": "hello",
        "product": "Top",
        "max_count": 10,
        "created_at": "2026-03-10T00:00:00+00:00",
        "preview_tweets": [{"id": "p1"}],
    }
    calls: list[str] = []

    def fake_summary(task_id: str):
        calls.append(f"summary:{task_id}")
        return dict(task)

    def fake_full(task_id: str):
        calls.append(f"full:{task_id}")
        return {**task, "tweets": [{"id": "t1"}]}

    monkeypatch.setattr(search.task_manager, "get_task_summary", fake_summary)
    monkeypatch.setattr(search.task_manager, "get_task_full", fake_full)

    result = asyncio.run(search.get_search_task("route-task", include_tweets=False))
    assert result.tweets == []
    assert calls == ["summary:route-task"]

    calls.clear()
    result = asyncio.run(search.get_search_task("route-task", include_tweets=True))
    assert len(result.tweets) == 1
    assert calls == ["full:route-task"]
