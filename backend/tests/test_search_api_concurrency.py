import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from api.main import app  # noqa: E402
from api.routers import search as search_router  # noqa: E402


client = TestClient(app)


def test_create_search_task_enqueues_when_over_runtime_window(monkeypatch):
    monkeypatch.setattr(
        search_router.task_manager,
        "create_task",
        lambda **kwargs: "task-1",
    )
    monkeypatch.setattr(
        search_router.task_manager,
        "get_task",
        lambda _task_id: {
            "task_id": "task-1",
            "status": "pending",
            "keyword": "ai",
            "product": "Top",
            "max_count": 0,
            "result_count": 0,
            "current_page": 0,
            "created_at": "2026-01-01T00:00:00+00:00",
            "risk_state": "none",
            "quality_state": "complete",
            "runtime_metrics": {},
            "last_event_at": "2026-01-01T00:00:00+00:00",
            "resumed": False,
            "fetch_replies": False,
            "crawl_strategy": "dfs",
            "max_replies_per_tweet": 0,
            "replies_fetched": 0,
            "tweets": [],
            "preview_tweets": [],
            "crawl_phase": "已加入调度队列，等待执行...",
        },
    )

    started = {"called": 0}

    def _fake_start_crawler_thread(*args, **kwargs):
        started["called"] += 1

    monkeypatch.setattr(search_router.crawl_service, "start_crawler_thread", _fake_start_crawler_thread)

    resp = client.post(
        "/api/v1/search",
        json={
            "keyword": "ai",
            "max_count": 0,
            "product": "Top",
            "resume": True,
            "fetch_replies": False,
            "max_replies_per_tweet": 0,
            "crawl_strategy": "dfs",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert started["called"] == 1

