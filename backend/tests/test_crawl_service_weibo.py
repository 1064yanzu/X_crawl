from types import SimpleNamespace

from api.services import crawl_service


def test_run_search_task_weibo_uses_real_reply_count(monkeypatch):
    captured = {}

    monkeypatch.setattr(crawl_service.task_manager, "update_task_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.task_manager, "update_task_phase", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.task_manager, "clear_thread", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.scheduler, "mark_done", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service, "ensure_browser_alive", lambda: None)
    monkeypatch.setattr(crawl_service, "reset_browser", lambda: None)
    monkeypatch.setattr(crawl_service, "start_task_metrics", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service, "get_metrics", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(crawl_service, "clear_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(crawl_service.telemetry, "record_event", lambda *args, **kwargs: None)

    monkeypatch.setattr(
        crawl_service,
        "_run_weibo_task",
        lambda **kwargs: SimpleNamespace(
            resumed=False,
            posts=[
                {
                    "id": "w1",
                    "comment_stats": {"fetched_total_count": 6},
                    "replies": [{"id": "r1"}, {"id": "r2"}],
                },
                {
                    "id": "w2",
                    "comment_stats": {"fetched_total_count": 4},
                    "replies": [{"id": "r3"}],
                },
            ],
        ),
    )

    def _capture_result(*, task_id, tweets, resumed, replies_fetched, quality_state, runtime_metrics):
        captured["task_id"] = task_id
        captured["replies_fetched"] = replies_fetched
        captured["tweets"] = tweets

    monkeypatch.setattr(crawl_service.task_manager, "update_task_result", _capture_result)

    crawl_service.run_search_task(
        task_id="weibo-task-1",
        keyword="AI",
        max_count=0,
        product="Top",
        platform="weibo",
        fetch_replies=True,
    )

    assert captured["task_id"] == "weibo-task-1"
    assert captured["replies_fetched"] == 10
    assert len(captured["tweets"]) == 2
