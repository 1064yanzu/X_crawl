from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_comment_backfill_task_reuses_primary_pool_browser_without_aux(monkeypatch):
    from api.services import crawl_service
    from crawler.comment_backfill_runner import CommentBackfillResult
    import config

    browser_instance = object()
    captured: dict[str, object] = {}

    class _DummyPool:
        def __init__(self) -> None:
            self.aux_calls = 0
            self.release_calls: list[str] = []

        def acquire(self, task_id: str, *, platform: str):
            captured["acquire"] = {"task_id": task_id, "platform": platform}
            return browser_instance, 0

        def acquire_aux(self, task_id: str, *, purpose: str):
            self.aux_calls += 1
            raise AssertionError("comment_backfill 不应再申请 aux 浏览器实例")

        def release(self, task_id: str) -> None:
            self.release_calls.append(task_id)

    dummy_pool = _DummyPool()

    monkeypatch.setattr(config.settings, "account_pool_enabled", False, raising=False)
    monkeypatch.setattr(crawl_service.task_manager, "update_task_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.task_manager, "update_task_phase", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.task_manager, "update_comment_backfill_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.task_manager, "update_task_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.task_manager, "clear_thread", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.task_queue_manager, "notify_task_terminal", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.telemetry, "record_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service, "start_task_metrics", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service, "clear_metrics", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service, "get_metrics", lambda *args, **kwargs: {})
    monkeypatch.setattr(crawl_service.scheduler, "mark_done", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service, "_release_task_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("crawler.browser_pool.is_pool_mode_enabled", lambda: True)
    monkeypatch.setattr("crawler.browser_pool.get_browser_pool", lambda: dummy_pool)

    def fake_run_comment_backfill_task(**kwargs):
        captured["browser_instance"] = kwargs.get("browser_instance")
        return CommentBackfillResult(
            tweets=[],
            replies_fetched=0,
            failed_records=[],
            progress={
                "total_posts": 0,
                "eligible_posts": 0,
                "processed_posts": 0,
                "skipped_posts": 0,
                "succeeded_posts": 0,
                "failed_posts": 0,
            },
        )

    monkeypatch.setattr(crawl_service, "run_comment_backfill_task", fake_run_comment_backfill_task)

    crawl_service.run_search_task(
        task_id="task-comment-backfill",
        keyword="X 评论补采 · OpenAI",
        product="Comments",
        resume=True,
        fetch_replies=True,
        max_replies_per_tweet=20,
        reply_depth=2,
        crawl_strategy="bfs",
        force_new_browser=False,
        platform="x",
        task_kind="comment_backfill",
    )

    assert captured["acquire"] == {"task_id": "task-comment-backfill", "platform": "x"}
    assert captured["browser_instance"] is browser_instance
    assert dummy_pool.aux_calls == 0
    assert dummy_pool.release_calls == ["task-comment-backfill"]
