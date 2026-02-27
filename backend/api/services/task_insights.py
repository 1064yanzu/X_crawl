"""任务数据洞察：时间覆盖范围与轻量汇总。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


def _parse_iso(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _span_hours(start: Optional[datetime], end: Optional[datetime]) -> float:
    if not start or not end:
        return 0.0
    delta = (end - start).total_seconds()
    if delta <= 0:
        return 0.0
    return round(delta / 3600.0, 2)


def summarize_tweets(tweets: list[dict]) -> tuple[int, dict]:
    """
    扫描推文与回复，产出：
    1) 回复总数（仅统计当前 tweets 列表里的 replies 长度）
    2) 时间覆盖范围（推文/回复/合并）
    """
    tweet_min: Optional[datetime] = None
    tweet_max: Optional[datetime] = None
    reply_min: Optional[datetime] = None
    reply_max: Optional[datetime] = None
    tweet_ts_count = 0
    reply_ts_count = 0
    replies_count = 0

    for tweet in tweets:
        tweet_dt = _parse_iso(tweet.get("created_at"))
        if tweet_dt:
            tweet_ts_count += 1
            tweet_min = tweet_dt if tweet_min is None else min(tweet_min, tweet_dt)
            tweet_max = tweet_dt if tweet_max is None else max(tweet_max, tweet_dt)

        replies = tweet.get("replies") or []
        if isinstance(replies, list):
            replies_count += len(replies)
            for reply in replies:
                if not isinstance(reply, dict):
                    continue
                reply_dt = _parse_iso(reply.get("created_at"))
                if not reply_dt:
                    continue
                reply_ts_count += 1
                reply_min = reply_dt if reply_min is None else min(reply_min, reply_dt)
                reply_max = reply_dt if reply_max is None else max(reply_max, reply_dt)

    merged_start = min([d for d in (tweet_min, reply_min) if d is not None], default=None)
    merged_end = max([d for d in (tweet_max, reply_max) if d is not None], default=None)

    coverage = {
        "tweet_start_at": _to_iso(tweet_min),
        "tweet_end_at": _to_iso(tweet_max),
        "tweet_span_hours": _span_hours(tweet_min, tweet_max),
        "tweet_ts_count": tweet_ts_count,
        "reply_start_at": _to_iso(reply_min),
        "reply_end_at": _to_iso(reply_max),
        "reply_span_hours": _span_hours(reply_min, reply_max),
        "reply_ts_count": reply_ts_count,
        "combined_start_at": _to_iso(merged_start),
        "combined_end_at": _to_iso(merged_end),
        "combined_span_hours": _span_hours(merged_start, merged_end),
    }
    return replies_count, coverage
