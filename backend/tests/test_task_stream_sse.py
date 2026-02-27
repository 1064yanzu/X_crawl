import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from api.main import app  # noqa: E402
from api.routers import tasks as tasks_router  # noqa: E402


client = TestClient(app)


def _task_payload() -> dict:
    return {
        "task_id": "task-stream-1",
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
        "live_metrics": {"tweets_per_min_15s": 1.5},
        "latest_action": {"type": "task_phase", "phase": "等待第 1 页数据包..."},
        "queue_position": None,
        "last_event_at": "2026-01-01T00:00:00+00:00",
        "resumed": False,
        "fetch_replies": False,
        "crawl_strategy": "dfs",
        "max_replies_per_tweet": 0,
        "reply_depth": 2,
        "replies_fetched": 0,
        "tweets": [],
        "preview_tweets": [],
        "crawl_phase": "等待第 1 页数据包...",
    }


def test_task_stream_emits_action_and_snapshot(monkeypatch):
    task = _task_payload()

    lookup = {"count": 0}

    def _get_task(_task_id: str):
        lookup["count"] += 1
        if lookup["count"] <= 4:
            return task
        return None

    monkeypatch.setattr(tasks_router.task_manager, "get_task", _get_task)

    sent_once = {"done": False}

    def _events(_task_id: str, *, after_id: int = 0, limit: int = 120):
        if not sent_once["done"] and after_id < 1:
            sent_once["done"] = True
            return [{"id": 1, "type": "task_phase", "phase": "等待第 1 页数据包...", "ts": "2026-01-01T00:00:00+00:00"}]
        return []

    monkeypatch.setattr(tasks_router.task_manager, "get_task_events", _events)
    monkeypatch.setattr(tasks_router.settings, "crawler_live_push_interval_ms", 200)

    got_action = False
    got_snapshot = False

    with client.stream("GET", "/api/v1/tasks/task-stream-1/stream") as resp:
        assert resp.status_code == 200
        for idx, line in enumerate(resp.iter_lines()):
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="ignore")
            if not line:
                continue
            if line.startswith("event: action"):
                got_action = True
            if line.startswith("event: snapshot"):
                got_snapshot = True
            if got_action and got_snapshot:
                break
            if idx > 40:
                break

    assert got_action is True
    assert got_snapshot is True
