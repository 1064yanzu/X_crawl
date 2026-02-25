import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from api.main import app  # noqa: E402
from api.routers import search as search_router  # noqa: E402


client = TestClient(app)


def test_create_search_task_returns_409_when_over_concurrency_limit(monkeypatch):
    monkeypatch.setattr(search_router.task_manager, "count_active_tasks", lambda: 1)
    monkeypatch.setattr(search_router.settings, "crawler_max_concurrent_tasks", 1)

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

    assert resp.status_code == 409
    assert "上限" in resp.json()["detail"]
