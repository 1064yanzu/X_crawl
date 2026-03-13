from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.services.comment_backfill_task_source import analyze_comment_backfill_task


def test_analyze_comment_backfill_task_filters_existing_replies_and_zero_reply_posts():
    task = {
        "task_id": "task-001",
        "task_kind": "search",
        "status": "done",
        "platform": "x",
        "keyword": "OpenAI",
        "tweets": [
            {
                "id": "1001",
                "text": "eligible",
                "url": "https://x.com/openai/status/1001",
                "author": {"screen_name": "openai", "name": "OpenAI"},
                "metrics": {"replies": 5, "likes": 10, "retweets": 2, "quotes": 1},
            },
            {
                "id": "1002",
                "text": "already fetched",
                "url": "https://x.com/openai/status/1002",
                "author": {"screen_name": "openai", "name": "OpenAI"},
                "metrics": {"replies": 7},
                "replies": [{"id": "r-1", "text": "hi"}],
            },
            {
                "id": "1003",
                "text": "zero reply",
                "url": "https://x.com/openai/status/1003",
                "author": {"screen_name": "openai", "name": "OpenAI"},
                "metrics": {"replies": 0},
            },
        ],
    }

    result = analyze_comment_backfill_task(task)

    assert result.summary["unique_post_count"] == 3
    assert result.summary["eligible_posts"] == 1
    assert result.summary["skipped_existing_comment_posts"] == 1
    assert result.summary["skipped_zero_comment_posts"] == 1
    assert result.tweets[0]["id"] == "1001"
    assert result.tweets[0].get("replies") is None


def test_analyze_comment_backfill_task_requires_done_search_task():
    task = {
        "task_id": "task-002",
        "task_kind": "comment_backfill",
        "status": "done",
        "platform": "x",
        "tweets": [],
    }

    with pytest.raises(HTTPException) as exc_info:
        analyze_comment_backfill_task(task)

    assert exc_info.value.status_code == 400
    assert "不是帖子采集任务" in str(exc_info.value.detail)
