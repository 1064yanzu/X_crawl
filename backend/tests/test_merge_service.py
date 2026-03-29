from api.services import merge_service
from api.services.task_manager import _merge_coverage


class _FakeTaskManager:
    def __init__(self, tasks: dict[str, dict]):
        self._tasks = tasks

    def get_task_summary(self, task_id: str):
        return self._tasks.get(task_id)


def test_find_mergeable_groups_merges_short_keyword_into_long_keyword(monkeypatch):
    tasks = {
        "task-a": {
            "task_id": "task-a",
            "status": "done",
            "platform": "x",
            "product": "Top",
            "task_kind": "search",
            "keyword": "ChatGPT",
            "created_at": "2026-03-05T00:00:00+00:00",
        },
        "task-b": {
            "task_id": "task-b",
            "status": "done",
            "platform": "x",
            "product": "Top",
            "task_kind": "search",
            "keyword": "ChatGPT since:2026-03-01 until:2026-03-05",
            "created_at": "2026-03-06T00:00:00+00:00",
        },
        "task-c": {
            "task_id": "task-c",
            "status": "done",
            "platform": "x",
            "product": "Top",
            "task_kind": "search",
            "keyword": "OpenAI",
            "created_at": "2026-03-07T00:00:00+00:00",
        },
        "task-d": {
            "task_id": "task-d",
            "status": "done",
            "platform": "x",
            "product": "Latest",
            "task_kind": "search",
            "keyword": "ChatGPT OR OpenAI",
            "created_at": "2026-03-08T00:00:00+00:00",
        },
    }

    monkeypatch.setattr(
        merge_service,
        "_get_task_manager",
        lambda: _FakeTaskManager(tasks),
    )

    groups, non_mergeable = merge_service.find_mergeable_groups(list(tasks))

    assert len(groups) == 1
    assert groups[0]["target_task_id"] == "task-d"
    assert groups[0]["source_task_ids"] == ["task-a", "task-b", "task-c"]
    assert set(non_mergeable) == set()


def test_merge_coverage_tolerates_none_ts_count():
    merged = _merge_coverage(
        {
            "tweet_start_at": "2026-03-01T00:00:00+00:00",
            "tweet_end_at": "2026-03-02T00:00:00+00:00",
            "tweet_ts_count": None,
            "reply_ts_count": 3,
        },
        {
            "tweet_start_at": "2026-03-03T00:00:00+00:00",
            "tweet_end_at": "2026-03-04T00:00:00+00:00",
            "tweet_ts_count": 5,
            "reply_ts_count": None,
        },
    )

    assert merged["tweet_start_at"] == "2026-03-01T00:00:00+00:00"
    assert merged["tweet_end_at"] == "2026-03-04T00:00:00+00:00"
    assert merged["tweet_ts_count"] == 5
    assert merged["reply_ts_count"] == 3
