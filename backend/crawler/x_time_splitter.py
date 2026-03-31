"""
X 搜索自动时间分割。

统一使用固定天数窗口切分时间范围：
- 达到触发阈值后按固定窗口切分
- 长跨度任务继续使用 unlimited_window_days 配置
- 复爬任务沿用同一套固定窗口规则
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
    window_days: int
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
    enabled: bool,
    trigger_days: int,
    window_days: int,
    unlimited_window_days: int,
    max_segments: int,
    force_window: bool = False,
) -> TimeSplitPlan:
    base_query, since, until = parse_query_time_range(query)
    if not enabled or not since or not until:
        return TimeSplitPlan(False, base_query, since, until, 0, ())

    start = _parse_date(since)
    end = _parse_date(until)
    if not start or not end or end <= start:
        return TimeSplitPlan(False, base_query, since, until, 0, ())

    span_days = (end - start).days
    if span_days < max(1, trigger_days):
        return TimeSplitPlan(False, base_query, since, until, 0, ())

    configured_window = max(1, int(unlimited_window_days))
    resolved_window = _resolve_window_days(span_days=span_days, configured_window=configured_window)
    resolved_max_segments = _resolve_max_segments(
        span_days=span_days,
        window_days=resolved_window,
        configured_limit=max_segments,
    )
    segments = _split_by_fixed_days(
        start,
        end,
        window_days=resolved_window,
        max_segments=resolved_max_segments,
    )

    if len(segments) <= 1:
        return TimeSplitPlan(False, base_query, since, until, 0, ())

    return TimeSplitPlan(
        enabled=True,
        base_query=base_query,
        original_since=since,
        original_until=until,
        window_days=resolved_window,
        segments=tuple(segments),
    )


def _resolve_window_days(*, span_days: int, configured_window: int) -> int:
    if span_days > 365:
        return 7
    return max(1, int(configured_window))


def _resolve_max_segments(*, span_days: int, window_days: int, configured_limit: int) -> int:
    """
    解析最终允许的最大分段数。

    规则：
    - 超过 1 年的长跨度任务，既然已经强制按 7 天切段，就不应再被历史残留的小上限配置打死。
      这类场景自动放宽到“至少覆盖本次所需分段数”。
    - 其余场景仍沿用显式安全上限，避免普通任务被误切成过多段。
    """
    limit = max(1, int(configured_limit))
    required_segments = max(1, (max(1, span_days) + max(1, window_days) - 1) // max(1, window_days))
    if span_days > 365:
        return max(limit, required_segments)
    return limit


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


def _split_by_fixed_days(
    start: datetime,
    end: datetime,
    *,
    window_days: int,
    max_segments: int,
) -> list[TimeSplitSegment]:
    """按固定天数分割时间范围。"""
    segments: list[TimeSplitSegment] = []
    current = start
    step = max(1, int(window_days))
    limit = max(1, int(max_segments))
    span_days = max(1, (end - start).days)
    required_segments = (span_days + step - 1) // step
    if required_segments > limit:
        raise ValueError(
            f"时间分段数量 {required_segments} 超过安全上限 {limit}，"
            "请缩小时间范围或提高最大分段数"
        )

    while current < end:
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
