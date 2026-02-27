import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from api.main import app  # noqa: E402
from api.routers import search as search_router  # noqa: E402
from api.routers import tasks as tasks_router  # noqa: E402


client = TestClient(app)


def _task_payload() -> dict:
    return {
        "task_id": "task-1",
        "status": "running",
        "keyword": "ai",
        "product": "Top",
        "max_count": 0,
        "result_count": 2,
        "current_page": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "risk_state": "none",
        "quality_state": "complete",
        "runtime_metrics": {},
        "last_event_at": "2026-01-01T00:00:00+00:00",
        "resumed": False,
        "fetch_replies": False,
        "crawl_strategy": "dfs",
        "max_replies_per_tweet": 0,
        "reply_depth": 2,
        "replies_fetched": 0,
        "tweets": [{"id": "a"}, {"id": "b"}],
        "preview_tweets": [{"id": "b"}],
        "crawl_phase": "等待第 1 页数据包...",
    }


def test_get_search_task_supports_lightweight_mode(monkeypatch):
    monkeypatch.setattr(search_router.task_manager, "get_task", lambda _task_id: _task_payload())

    resp = client.get("/api/v1/search/task-1?include_tweets=false")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tweets"] == []
    assert data["preview_tweets"] == [{"id": "b"}]


def test_list_tasks_supports_summary_mode(monkeypatch):
    monkeypatch.setattr(tasks_router.task_manager, "list_tasks", lambda: [_task_payload()])

    resp = client.get("/api/v1/tasks?include_payload=false")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["tweets"] == []
    assert data[0]["preview_tweets"] == []

