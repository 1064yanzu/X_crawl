from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.comment_backfill_runner import (
    CommentBackfillResult,
    _resolve_source_task_id,
    run_comment_backfill_task,
)


def test_comment_backfill_runner_falls_back_to_source_task(monkeypatch):
    source_task = {
        "task_id": "search-task-001",
        "task_kind": "search",
        "status": "done",
        "platform": "weibo",
        "keyword": "MiniMax",
        "tweets": [
            {
                "id": "1001",
                "text": "需要补采评论",
                "url": "https://weibo.com/detail/1001",
                "author": {"id": "u-1", "screen_name": "minimax", "name": "MiniMax"},
                "metrics": {"replies": 8},
            }
        ],
    }
    current_task = {
        "task_id": "backfill-task-001",
        "task_kind": "comment_backfill",
        "status": "pending",
        "platform": "weibo",
        "source_task_id": "search-task-001",
        "tweets": [],
    }
    seeded: list[tuple[str, list[dict], int]] = []
    received: list[dict] = []

    def fake_get_task_full(task_id: str):
        if task_id == "backfill-task-001":
            return current_task
        if task_id == "search-task-001":
            return source_task
        return None

    def fake_set_task_seed_tweets(task_id: str, tweets: list[dict], *, current_page: int = 0):
        seeded.append((task_id, tweets, current_page))

    browser_instance = object()

    def fake_run_weibo_comment_backfill(*, task_id: str, tweets: list[dict], browser_instance=None):
        received.append({"task_id": task_id, "tweets": tweets, "browser_instance": browser_instance})
        return CommentBackfillResult(
            tweets=tweets,
            replies_fetched=0,
            failed_records=[],
            progress={"total_posts": len(tweets), "eligible_posts": len(tweets), "processed_posts": 0, "skipped_posts": 0, "succeeded_posts": 0, "failed_posts": 0},
        )

    monkeypatch.setattr("crawler.comment_backfill_runner.task_manager.get_task_full", fake_get_task_full)
    monkeypatch.setattr("crawler.comment_backfill_runner.task_manager.set_task_seed_tweets", fake_set_task_seed_tweets)
    monkeypatch.setattr("crawler.comment_backfill_runner._run_weibo_comment_backfill", fake_run_weibo_comment_backfill)

    result = run_comment_backfill_task(
        task_id="backfill-task-001",
        platform="weibo",
        max_replies_per_tweet=0,
        reply_depth=2,
        browser_instance=browser_instance,
    )

    assert result.tweets[0]["id"] == "1001"
    assert seeded == [("backfill-task-001", result.tweets, 0)]
    assert received == [{"task_id": "backfill-task-001", "tweets": result.tweets, "browser_instance": browser_instance}]


def test_comment_backfill_runner_still_rejects_empty_task_without_source(monkeypatch):
    monkeypatch.setattr(
        "crawler.comment_backfill_runner.task_manager.get_task_full",
        lambda task_id: {
            "task_id": task_id,
            "task_kind": "comment_backfill",
            "status": "pending",
            "platform": "weibo",
            "tweets": [],
        },
    )

    with pytest.raises(RuntimeError) as exc_info:
        run_comment_backfill_task(
            task_id="backfill-task-empty",
            platform="weibo",
            max_replies_per_tweet=0,
            reply_depth=2,
        )

    assert "没有可处理的帖子" in str(exc_info.value)


def test_comment_backfill_runner_infers_source_task_id_for_legacy_tasks(monkeypatch):
    current_task = {
        "task_id": "backfill-task-legacy",
        "task_kind": "comment_backfill",
        "status": "failed",
        "platform": "weibo",
        "keyword": "微博 评论补采 · MiniMax",
        "created_at": "2026-03-15T04:05:29+00:00",
        "tweets": [],
    }
    source_task = {
        "task_id": "search-task-minimax",
        "task_kind": "search",
        "status": "done",
        "platform": "weibo",
        "keyword": "MiniMax",
        "created_at": "2026-03-14T04:00:00+00:00",
        "tweets": [
            {
                "id": "1001",
                "text": "需要补采评论",
                "url": "https://weibo.com/detail/1001",
                "author": {"id": "u-1", "screen_name": "minimax", "name": "MiniMax"},
                "metrics": {"replies": 3},
            }
        ],
        "result_count": 1,
    }
    updated_source_ids: list[tuple[str, str | None]] = []

    def fake_get_task_full(task_id: str):
        if task_id == "backfill-task-legacy":
            return current_task
        if task_id == "search-task-minimax":
            return source_task
        return None

    monkeypatch.setattr("crawler.comment_backfill_runner.task_manager.get_task_full", fake_get_task_full)
    monkeypatch.setattr(
        "crawler.comment_backfill_runner.task_manager.list_tasks",
        lambda include_payload=False: [current_task, source_task],
    )
    monkeypatch.setattr(
        "crawler.comment_backfill_runner.task_manager.update_task_source_task_id",
        lambda task_id, source_task_id: updated_source_ids.append((task_id, source_task_id)),
    )

    resolved = _resolve_source_task_id(
        task_id="backfill-task-legacy",
        task=current_task,
    )

    assert resolved == "search-task-minimax"
    assert updated_source_ids == [("backfill-task-legacy", "search-task-minimax")]
