"""
X 搜索自动时间分割。

根据搜索的时间跨度自适应选择分割粒度：
- 跨度较短时使用用户配置的 window_days
- 跨度较长时（≥90 天）自动升级到按月分割，避免分段过多触发反爬
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


_SINCE_RE = re.compile(r"^since:(\d{4}-\d{2}-\d{2})$", re.IGNORECASE)
_UNTIL_RE = re.compile(r"^until:(\d{4}-\d{2}-\d{2})$", re.IGNORECASE)

# 自适应窗口阈值：超过此天数后切换到按月分割
_MONTHLY_SPLIT_THRESHOLD_DAYS = 90


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


def _compute_adaptive_window(span_days: int, configured_window: int) -> int:
    """根据时间跨度自适应计算实际窗口天数。

    策略：
    - 跨度 < 90 天：使用用户配置的 window_days（如 7/14 天）
    - 跨度 ≥ 90 天：升级到 30 天（按月级别），避免分段过多触发反爬
    """
    if span_days < _MONTHLY_SPLIT_THRESHOLD_DAYS:
        return max(1, configured_window)
    # 跨度 ≥ 90 天：至少按 30 天分
    return max(30, configured_window)


def build_time_split_plan(
    query: str,
    *,
    max_count: int,
    enabled: bool,
    trigger_days: int,
    window_days: int,
    unlimited_window_days: int,
    max_segments: int,
    force_window: bool = False,
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

    configured_window = max(1, unlimited_window_days if max_count == 0 else window_days)

    # force_window=True（复爬模式）：不自适应升级，强制使用 configured_window
    if force_window:
        segments = _split_by_fixed_days(start, end, window_days=configured_window, max_segments=max_segments)
    elif span_days >= _MONTHLY_SPLIT_THRESHOLD_DAYS:
        # 当跨度 ≥ 90 天时使用按自然月分割
        segments = _split_by_calendar_month(start, end, max_segments=max_segments)
    else:
        adaptive_window = _compute_adaptive_window(span_days, configured_window)
        segments = _split_by_fixed_days(start, end, window_days=adaptive_window, max_segments=max_segments)

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


def _split_by_calendar_month(
    start: datetime,
    end: datetime,
    *,
    max_segments: int,
) -> list[TimeSplitSegment]:
    """按自然月边界分割时间范围。

    每个 segment 从某月某日到下月同一日（或月末），
    对齐到自然月边界更符合直觉，且每段约 28-31 天，
    避免了固定天数分割导致的过多分段。
    """
    segments: list[TimeSplitSegment] = []
    total_limit = max(1, max_segments)
    current = start

    while current < end and len(segments) < total_limit:
        # 计算下一个月的同一天
        next_month = _add_one_month(current)
        segment_end = min(next_month, end)

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


def _split_by_fixed_days(
    start: datetime,
    end: datetime,
    *,
    window_days: int,
    max_segments: int,
) -> list[TimeSplitSegment]:
    """按固定天数分割时间范围（用于短跨度场景）。"""
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


def _add_one_month(dt: datetime) -> datetime:
    """给定日期加一个自然月。例如 2024-01-15 -> 2024-02-15，
    若目标月没有对应日期则取月末（如 1-31 -> 2-28/29）。"""
    year = dt.year
    month = dt.month + 1
    if month > 12:
        month = 1
        year += 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, max_day)
    return dt.replace(year=year, month=month, day=day)


def _parse_date(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
