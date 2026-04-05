from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_comment_backfill_task_acquires_reply_browser_in_pool_mode(monkeypatch):
    """pool 模式下，comment_backfill 任务应同时申请主浏览器实例和 aux 浏览器实例（供 pipeline nested_worker 使用）。"""
    from api.services import crawl_service
    from crawler.comment_backfill_runner import CommentBackfillResult
    import config

    browser_instance = object()
    reply_browser_instance = object()
    captured: dict[str, object] = {}

    class _DummyPool:
        def __init__(self) -> None:
            self.aux_calls: list[dict] = []
            self.release_calls: list[str] = []

        def acquire(self, task_id: str, *, platform: str):
            captured["acquire"] = {"task_id": task_id, "platform": platform}
            return browser_instance, 0

        def acquire_aux(self, task_id: str, *, purpose: str):
            self.aux_calls.append({"task_id": task_id, "purpose": purpose})
            return reply_browser_instance

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
        captured["reply_browser_instance"] = kwargs.get("reply_browser_instance")
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
    # 优化后：补采任务不再申请额外 aux 浏览器（主实例在补采期间空闲，可复用）
    assert len(dummy_pool.aux_calls) == 0
    assert captured["reply_browser_instance"] is None
    assert dummy_pool.release_calls == ["task-comment-backfill"]
