"""任务数据洞察：时间覆盖范围与轻量汇总。"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

# 默认时区：中国标准时间 (UTC+8)，微博数据默认在此时区
_CST = timezone(timedelta(hours=8))


def _parse_iso(value: object) -> Optional[datetime]:
    """
    解析多种日期格式，始终返回 timezone-aware datetime。
    无时区信息的日期默认视为 CST (UTC+8)。
    """
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    dt: Optional[datetime] = None

    # ISO 格式
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        pass

    # 微博搜索结果的中文日期格式：2023年12月31日 22:57
    if dt is None:
        import re
        m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})", text)
        if m:
            try:
                dt = datetime(
                    int(m.group(1)), int(m.group(2)), int(m.group(3)),
                    int(m.group(4)), int(m.group(5))
                )
            except ValueError:
                pass

    # 微博评论 API 的英文日期格式：Mon Jan 01 00:04:47 +0800 2024
    if dt is None:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(text)
        except Exception:
            pass

    # 尝试常见中文格式：2023-12-31 22:57:00
    if dt is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                pass

    if dt is None:
        return None

    # 统一转为 timezone-aware，无时区信息的默认为 CST
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_CST)

    return dt


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

    def _walk_replies(nodes: list[dict]) -> None:
        nonlocal replies_count, reply_min, reply_max, reply_ts_count
        for reply in nodes:
            if not isinstance(reply, dict):
                continue
            replies_count += 1
            reply_dt = _parse_iso(reply.get("created_at"))
            if reply_dt:
                reply_ts_count += 1
                reply_min = reply_dt if reply_min is None else min(reply_min, reply_dt)
                reply_max = reply_dt if reply_max is None else max(reply_max, reply_dt)
            nested = reply.get("replies") or []
            if isinstance(nested, list) and nested:
                _walk_replies(nested)

    for tweet in tweets:
        tweet_dt = _parse_iso(tweet.get("created_at"))
        if tweet_dt:
            tweet_ts_count += 1
            tweet_min = tweet_dt if tweet_min is None else min(tweet_min, tweet_dt)
            tweet_max = tweet_dt if tweet_max is None else max(tweet_max, tweet_dt)

        replies = tweet.get("replies") or []
        if isinstance(replies, list):
            _walk_replies(replies)

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
