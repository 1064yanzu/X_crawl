"""
X 搜索自动时间分割。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


_SINCE_RE = re.compile(r"^since:(\d{4}-\d{2}-\d{2})$", re.IGNORECASE)
_UNTIL_RE = re.compile(r"^until:(\d{4}-\d{2}-\d{2})$", re.IGNORECASE)


@dataclass(frozen=True)
class TimeSplitSegment:
    since: str
    until: str


@dataclass(frozen=True)
class TimeSplitPlan:
    enabled: bool
    base_query: str
    original_since: Optional[str]
    original_until: Optional[str]
    segments: tuple[TimeSplitSegment, ...]


def parse_query_time_range(query: str) -> tuple[str, Optional[str], Optional[str]]:
    tokens = query.split()
    since = None
    until = None
    base_tokens: list[str] = []
    for token in tokens:
        m_since = _SINCE_RE.match(token)
        if m_since:
            since = m_since.group(1)
            continue
        m_until = _UNTIL_RE.match(token)
        if m_until:
            until = m_until.group(1)
            continue
        base_tokens.append(token)
    return " ".join(base_tokens).strip(), since, until


def build_query_with_window(base_query: str, since: str, until: str) -> str:
    suffix = f"since:{since} until:{until}"
    return f"{base_query} {suffix}".strip()


def build_time_split_plan(
    query: str,
    *,
    max_count: int,
    enabled: bool,
    trigger_days: int,
    window_days: int,
    unlimited_window_days: int,
    max_segments: int,
) -> TimeSplitPlan:
    base_query, since, until = parse_query_time_range(query)
    if not enabled or not since or not until:
        return TimeSplitPlan(False, base_query, since, until, ())

    start = _parse_date(since)
    end = _parse_date(until)
    if not start or not end or end <= start:
        return TimeSplitPlan(False, base_query, since, until, ())

    span_days = (end - start).days
    if span_days < max(1, trigger_days):
        return TimeSplitPlan(False, base_query, since, until, ())

    window = max(1, unlimited_window_days if max_count == 0 else window_days)
    segments = _split_date_range(start, end, window_days=window, max_segments=max_segments)
    if len(segments) <= 1:
        return TimeSplitPlan(False, base_query, since, until, ())

    return TimeSplitPlan(
        enabled=True,
        base_query=base_query,
        original_since=since,
        original_until=until,
        segments=tuple(segments),
    )


def serialize_segments(segments: tuple[TimeSplitSegment, ...] | list[TimeSplitSegment]) -> list[dict]:
    return [{"since": seg.since, "until": seg.until} for seg in segments]


def deserialize_segments(items: list[dict] | tuple[dict, ...] | None) -> tuple[TimeSplitSegment, ...]:
    if not items:
        return ()
    segments: list[TimeSplitSegment] = []
    for item in items:
        since = str(item.get("since", "")).strip()
        until = str(item.get("until", "")).strip()
        if since and until:
            segments.append(TimeSplitSegment(since=since, until=until))
    return tuple(segments)


def _split_date_range(
    start: datetime,
    end: datetime,
    *,
    window_days: int,
    max_segments: int,
) -> list[TimeSplitSegment]:
    segments: list[TimeSplitSegment] = []
    current = start
    total_limit = max(1, max_segments)
    step = max(1, int(window_days))

    while current < end and len(segments) < total_limit:
        raw_end = current + timedelta(days=step)
        segment_end = min(raw_end, end)
        segments.append(
            TimeSplitSegment(
                since=current.strftime("%Y-%m-%d"),
                until=segment_end.strftime("%Y-%m-%d"),
            )
        )
        if segment_end >= end:
            break
        current = segment_end

    return segments


def _parse_date(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
