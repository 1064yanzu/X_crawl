from api.routers.tasks import _strip_weibo_time_syntax
from api.routers.tasks import _do_recrawl_task


def test_strip_weibo_time_syntax_keeps_or_keywords() -> None:
    assert _strip_weibo_time_syntax("ChatGPT OR OpenAI since:2022-09-01 until:2026-03-05") == "ChatGPT OR OpenAI"


def test_strip_weibo_time_syntax_keeps_plain_keyword() -> None:
    assert _strip_weibo_time_syntax("Claude") == "Claude"


def test_do_recrawl_task_reuses_existing_weibo_task(monkeypatch) -> None:
    original = {
        "task_id": "task-weibo-1",
        "status": "done",
        "keyword": "ChatGPT since:2022-09-01 until:2026-03-05",
        "max_count": 100,
        "product": "Top",
        "fetch_replies": True,
        "max_replies_per_tweet": 0,
        "reply_depth": 2,
        "crawl_strategy": "dfs",
        "platform": "weibo",
        "start_date": "2022-09-01",
        "end_date": "2026-03-05",
        "source_task_id": None,
    }
    seed_tweets = [{"id": "1"}, {"id": "2"}]
    prepared_calls: list[dict] = []
    started_calls: list[dict] = []
    summary_call_count = {"count": 0}

    def fake_get_task_summary(task_id: str):
        if task_id != "task-weibo-1":
            return None
        summary_call_count["count"] += 1
        if summary_call_count["count"] == 1:
            return dict(original)
        return {**original, "keyword": "ChatGPT"}

    monkeypatch.setattr("api.routers.tasks.task_manager.get_task_summary", fake_get_task_summary)
    monkeypatch.setattr(
        "api.routers.tasks.task_manager._get_task_result_snapshot",
        lambda task_id, load=False: seed_tweets if task_id == "task-weibo-1" else [],
    )

    def fake_prepare(task_id: str, **kwargs):
        prepared_calls.append({"task_id": task_id, **kwargs})
        return True

    monkeypatch.setattr("api.routers.tasks.task_manager.prepare_task_for_recrawl", fake_prepare)

    def fake_start(task_id: str, task: dict, resume: bool = True, **kwargs):
        started_calls.append({"task_id": task_id, "task": task, "resume": resume})

    monkeypatch.setattr("api.routers.tasks.crawl_service.start_crawler_thread", fake_start)

    target_task_id, exclude_count, error, reused_existing = _do_recrawl_task("task-weibo-1")

    assert error is None
    assert reused_existing is True
    assert target_task_id == "task-weibo-1"
    assert exclude_count == 2
    assert prepared_calls[0]["keyword"] == "ChatGPT"
    assert prepared_calls[0]["exclude_tweet_ids"] == ["1", "2"]
    assert started_calls[0]["task_id"] == "task-weibo-1"
    assert started_calls[0]["resume"] is False


def test_do_recrawl_task_reuses_root_x_task(monkeypatch) -> None:
    original = {
        "task_id": "task-x-1",
        "status": "done",
        "keyword": "OpenAI since:2022-06-01 until:2026-03-25",
        "max_count": 100,
        "product": "Top",
        "fetch_replies": True,
        "max_replies_per_tweet": 0,
        "reply_depth": 2,
        "crawl_strategy": "dfs",
        "platform": "x",
        "start_date": "2022-06-01",
        "end_date": "2026-03-25",
        "source_task_id": None,
    }
    prepared_calls: list[dict] = []
    started_calls: list[dict] = []

    monkeypatch.setattr(
        "api.routers.tasks.task_manager.get_task_summary",
        lambda task_id: dict(original) if task_id == "task-x-1" else None,
    )
    monkeypatch.setattr(
        "api.routers.tasks.task_manager._get_task_result_snapshot",
        lambda task_id, load=False: [{"id": "1"}, {"id": "2"}] if task_id == "task-x-1" else [],
    )

    def fake_prepare(task_id: str, **kwargs):
        prepared_calls.append({"task_id": task_id, **kwargs})
        return True

    monkeypatch.setattr("api.routers.tasks.task_manager.prepare_task_for_recrawl", fake_prepare)

    def fake_start(task_id: str, task: dict, resume: bool = True, **kwargs):
        started_calls.append({"task_id": task_id, "task": task, "resume": resume})

    monkeypatch.setattr("api.routers.tasks.crawl_service.start_crawler_thread", fake_start)

    target_task_id, exclude_count, error, reused_existing = _do_recrawl_task("task-x-1")

    assert error is None
    assert reused_existing is True
    assert target_task_id == "task-x-1"
    assert exclude_count == 2
    assert prepared_calls[0]["task_id"] == "task-x-1"
    assert prepared_calls[0]["source_task_id"] == "task-x-1"
    assert prepared_calls[0]["exclude_tweet_ids"] == ["1", "2"]
    assert started_calls[0]["task_id"] == "task-x-1"
    assert started_calls[0]["resume"] is False


def test_do_recrawl_task_recrawl_child_routes_back_to_root_task(monkeypatch) -> None:
    child_task = {
        "task_id": "task-x-child",
        "status": "done",
        "keyword": "Claude",
        "max_count": 100,
        "product": "Latest",
        "fetch_replies": False,
        "max_replies_per_tweet": 20,
        "reply_depth": 2,
        "crawl_strategy": "dfs",
        "platform": "x",
        "start_date": "2026-03-01",
        "end_date": "2026-03-29",
        "source_task_id": "task-x-root",
    }
    root_task = {
        **child_task,
        "task_id": "task-x-root",
        "source_task_id": None,
    }
    prepared_calls: list[dict] = []
    started_calls: list[dict] = []

    def fake_get_task_summary(task_id: str):
        if task_id == "task-x-child":
            return dict(child_task)
        if task_id == "task-x-root":
            return dict(root_task)
        return None

    monkeypatch.setattr("api.routers.tasks.task_manager.get_task_summary", fake_get_task_summary)
    monkeypatch.setattr(
        "api.routers.tasks.task_manager._get_task_result_snapshot",
        lambda task_id, load=False: [{"id": "root-1"}] if task_id == "task-x-root" else [],
    )

    def fake_prepare(task_id: str, **kwargs):
        prepared_calls.append({"task_id": task_id, **kwargs})
        return True

    monkeypatch.setattr("api.routers.tasks.task_manager.prepare_task_for_recrawl", fake_prepare)

    def fake_start(task_id: str, task: dict, resume: bool = True, **kwargs):
        started_calls.append({"task_id": task_id, "task": task, "resume": resume})

    monkeypatch.setattr("api.routers.tasks.crawl_service.start_crawler_thread", fake_start)

    target_task_id, exclude_count, error, reused_existing = _do_recrawl_task("task-x-child")

    assert error is None
    assert reused_existing is True
    assert target_task_id == "task-x-root"
    assert exclude_count == 1
    assert prepared_calls[0]["task_id"] == "task-x-root"
    assert prepared_calls[0]["source_task_id"] == "task-x-root"
    assert prepared_calls[0]["exclude_tweet_ids"] == ["root-1"]
    assert started_calls[0]["task_id"] == "task-x-root"
    assert started_calls[0]["resume"] is False
