import json
import sqlite3
from pathlib import Path

from api.services import task_db


def _close_thread_local_conn() -> None:
    conn = getattr(task_db._local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        finally:
            delattr(task_db._local, "conn")


def test_save_task_summary_does_not_overwrite_tweets_json(tmp_path: Path):
    db_path = tmp_path / "tasks.db"
    _close_thread_local_conn()
    task_db.init_db(db_path)

    base_task = {
        "task_id": "t1",
        "status": "running",
        "keyword": "ai",
        "product": "Top",
        "max_count": 0,
        "result_count": 2,
        "current_page": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "finished_at": None,
        "error": None,
        "risk_state": "none",
        "quality_state": "complete",
        "runtime_metrics": {},
        "last_event_at": "2026-01-01T00:00:00+00:00",
        "resumed": False,
        "fetch_replies": False,
        "max_replies_per_tweet": 0,
        "crawl_strategy": "dfs",
        "replies_fetched": 0,
        "crawl_phase": "running",
        "tweets": [{"id": "a"}, {"id": "b"}],
        "preview_tweets": [{"id": "b"}],
    }
    task_db.save_task(base_task)

    summary_task = dict(base_task)
    summary_task["result_count"] = 3
    summary_task["current_page"] = 2
    summary_task["tweets"] = [{"id": "x-should-not-write"}]
    summary_task["preview_tweets"] = [{"id": "c"}]
    task_db.save_task_summary(summary_task)

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT tweets_json, preview_json, result_count, current_page FROM tasks WHERE task_id = ?",
            ("t1",),
        ).fetchone()

    tweets_json, preview_json, result_count, current_page = row
    tweets = json.loads(tweets_json)
    preview = json.loads(preview_json)

    assert tweets == [{"id": "a"}, {"id": "b"}]
    assert preview == [{"id": "c"}]
    assert result_count == 3
    assert current_page == 2

