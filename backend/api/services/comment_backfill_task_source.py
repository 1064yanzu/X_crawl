from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlparse

from fastapi import HTTPException

Platform = Literal["x", "weibo"]


@dataclass
class CommentBackfillTaskAnalysisResult:
    summary: dict
    tweets: list[dict]


def analyze_comment_backfill_task(task: dict) -> CommentBackfillTaskAnalysisResult:
    task_id = str(task.get("task_id") or "").strip()
    task_kind = str(task.get("task_kind") or "search").strip()
    status = str(task.get("status") or "").strip()
    platform = _normalize_platform(task.get("platform"))
    tweets = task.get("tweets") or []

    if task_kind != "search":
        raise HTTPException(status_code=400, detail=f"任务 {task_id or '--'} 不是帖子采集任务，不能直接发起评论补采")
    if status != "done":
        raise HTTPException(status_code=400, detail=f"任务 {task_id or '--'} 尚未完成，当前状态为 {status or '--'}")
    if platform is None:
        raise HTTPException(status_code=400, detail=f"任务 {task_id or '--'} 缺少可识别的平台信息")
    if not isinstance(tweets, list) or not tweets:
        raise HTTPException(status_code=400, detail=f"任务 {task_id or '--'} 没有可用于评论补采的帖子结果")

    seen_ids: set[str] = set()
    unique_posts = 0
    skipped_zero_comment_posts = 0
    skipped_invalid_posts = 0
    skipped_existing_comment_posts = 0
    deduplicated_posts = 0
    eligible_tweets: list[dict] = []

    for item in tweets:
        if not isinstance(item, dict):
            skipped_invalid_posts += 1
            continue

        seed = _build_seed_tweet_from_task(item, platform)
        if seed is None:
            skipped_invalid_posts += 1
            continue

        tweet_id = str(seed.get("id") or "").strip()
        if tweet_id in seen_ids:
            deduplicated_posts += 1
            continue
        seen_ids.add(tweet_id)
        unique_posts += 1

        reply_count = int((seed.get("metrics") or {}).get("replies") or 0)
        if reply_count <= 0:
            skipped_zero_comment_posts += 1
            continue

        if _has_existing_replies(item):
            skipped_existing_comment_posts += 1
            continue

        eligible_tweets.append(seed)

    summary = {
        "source_task_id": task_id,
        "source_keyword": str(task.get("keyword") or "").strip(),
        "platform": platform,
        "task_status": status,
        "result_count": len(tweets),
        "unique_post_count": unique_posts,
        "eligible_posts": len(eligible_tweets),
        "skipped_zero_comment_posts": skipped_zero_comment_posts,
        "skipped_invalid_posts": skipped_invalid_posts,
        "skipped_existing_comment_posts": skipped_existing_comment_posts,
        "deduplicated_posts": deduplicated_posts,
    }
    return CommentBackfillTaskAnalysisResult(summary=summary, tweets=eligible_tweets)


def _build_seed_tweet_from_task(tweet: dict, platform: Platform) -> Optional[dict]:
    seed = copy.deepcopy(tweet)
    tweet_id = _clean_str(seed.get("id"))
    if not tweet_id:
        return None

    url = _clean_str(seed.get("url"))
    author = seed.get("author") if isinstance(seed.get("author"), dict) else {}
    metrics = seed.get("metrics") if isinstance(seed.get("metrics"), dict) else {}
    author_id = _clean_str(author.get("id"))
    author_name = _clean_str(author.get("name"))
    author_username = _derive_screen_name(
        _clean_str(author.get("screen_name")),
        url=url,
        platform=platform,
    )

    if platform == "x" and not author_username:
        return None
    if platform == "weibo" and not (author_id or url):
        return None

    seed["id"] = tweet_id
    seed["platform"] = platform
    seed["conversation_id"] = _clean_str(seed.get("conversation_id"))
    seed["created_at"] = _clean_str(seed.get("created_at"))
    seed["source"] = _clean_str(seed.get("source"))
    seed["text"] = _clean_str(seed.get("text"))
    seed["lang"] = _clean_str(seed.get("lang"))
    seed["url"] = url
    seed["author"] = {
        "id": author_id,
        "name": author_name or author_username,
        "screen_name": author_username or author_name,
        "verified": bool(author.get("verified")),
        "followers_count": _to_int(author.get("followers_count")),
    }
    seed["metrics"] = {
        "likes": _to_int(metrics.get("likes")),
        "retweets": _to_int(metrics.get("retweets")),
        "replies": _to_int(metrics.get("replies")),
        "quotes": _to_int(metrics.get("quotes")),
        "views": _nullable_int(metrics.get("views")),
        "bookmarks": _to_int(metrics.get("bookmarks")),
    }
    seed["hashtags"] = [item for item in seed.get("hashtags", []) if isinstance(item, str)]
    seed["user_mentions"] = [
        mention for mention in seed.get("user_mentions", [])
        if isinstance(mention, dict)
    ]
    seed["media"] = [
        media for media in seed.get("media", [])
        if isinstance(media, dict)
    ]
    seed["is_retweet"] = bool(seed.get("is_retweet"))
    seed["is_quote"] = bool(seed.get("is_quote"))
    seed.pop("replies", None)
    seed.pop("comment_backfill_failed", None)
    seed.pop("comment_stats", None)
    return seed


def _has_existing_replies(tweet: dict) -> bool:
    replies = tweet.get("replies")
    if isinstance(replies, list) and len(replies) > 0:
        return True

    comment_stats = tweet.get("comment_stats")
    if isinstance(comment_stats, dict):
        fetched_total = _to_int(comment_stats.get("fetched_total_count"))
        fetched_top_level = _to_int(comment_stats.get("fetched_top_level_count"))
        if fetched_total > 0 or fetched_top_level > 0:
            return True
    return False


def _normalize_platform(value: object) -> Optional[Platform]:
    text = _clean_str(value).lower()
    if text in {"x", "twitter"}:
        return "x"
    if text in {"weibo", "微博"}:
        return "weibo"
    return None


def _derive_screen_name(raw: str, *, url: str, platform: Platform) -> str:
    if raw:
        return raw.lstrip("@")
    if not url:
        return ""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if platform == "x" and len(parts) >= 3 and parts[1] == "status":
        return parts[0].lstrip("@")
    return ""


def _to_int(value: object) -> int:
    text = _clean_str(value)
    if not text:
        return 0
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        return 0


def _nullable_int(value: object) -> Optional[int]:
    text = _clean_str(value)
    if not text:
        return None
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        return None


def _clean_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()
