"""任务级时间拆分策略解析。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from config import settings
from crawler.x_time_splitter import parse_query_time_range

TimeSplitMode = Literal["inherit", "on", "off"]


@dataclass(frozen=True)
class ResolvedTaskTimeSplit:
    mode: TimeSplitMode
    enabled: bool
    has_time_range: bool
    trigger_days: int
    window_days: int
    max_segments: int
    force_window: bool


def normalize_time_split_mode(value: object) -> TimeSplitMode:
    text = str(value or "").strip().lower()
    if text in {"on", "off", "inherit"}:
        return text  # type: ignore[return-value]
    return "inherit"


def resolve_task_time_split(
    *,
    platform: str,
    keyword: str,
    start_date: Optional[str],
    end_date: Optional[str],
    time_split_mode: object,
    time_split_window_days: Optional[int],
    time_split_max_segments: Optional[int],
) -> ResolvedTaskTimeSplit:
    mode = normalize_time_split_mode(time_split_mode)

    if platform == "weibo":
        has_time_range = bool(start_date and end_date)
        window_days = max(1, int(time_split_window_days or settings.weibo_time_split_window_days))
        max_segments = max(1, int(time_split_max_segments or settings.weibo_time_split_max_segments))
        enabled = has_time_range and mode != "off"
        return ResolvedTaskTimeSplit(
            mode=mode,
            enabled=enabled,
            has_time_range=has_time_range,
            trigger_days=1,
            window_days=window_days,
            max_segments=max_segments,
            force_window=mode == "on",
        )

    _base_query, since, until = parse_query_time_range(keyword)
    has_time_range = bool(since and until)
    window_days = max(1, int(time_split_window_days or settings.x_time_split_window_days_unlimited))
    max_segments = max(1, int(time_split_max_segments or settings.x_time_split_max_segments))
    enabled = has_time_range and mode != "off" and bool(settings.x_auto_time_split_enabled or mode == "on")
    trigger_days = 1 if mode == "on" else max(1, int(settings.x_time_split_trigger_days))

    return ResolvedTaskTimeSplit(
        mode=mode,
        enabled=enabled,
        has_time_range=has_time_range,
        trigger_days=trigger_days,
        window_days=window_days,
        max_segments=max_segments,
        force_window=mode == "on",
    )
