"""
日期范围分割器。
用于将大范围日期拆分为多个小范围，以突破微博搜索 50 页限制。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def split_date_range(
    start_date: str,
    end_date: str,
    max_pages: int = 50,
    total_pages_first_query: int = 0,
    target_count: int = 100,
    window_days: int = 7,
    max_segments: int = 600,
) -> list[tuple[str, str]]:
    """
    根据日期范围按固定窗口分割为多个子范围。

    Args:
        start_date: 开始日期（YYYY-MM-DD）
        end_date: 结束日期（YYYY-MM-DD）
        max_pages: 兼容保留参数
        total_pages_first_query: 兼容保留参数
        target_count: 兼容保留参数
        window_days: 每个时间窗口覆盖天数
        max_segments: 安全上限，超出时显式报错，不做静默截断

    Returns:
        日期范围列表 [(start, end), ...]，每个范围格式为 YYYY-MM-DD
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        logger.warning(f"无法解析日期范围: {start_date} ~ {end_date}，不分割")
        return [(start_date, end_date)]

    if start >= end:
        return [(start_date, end_date)]

    step = max(1, int(window_days))
    total_days = (end - start).days
    if total_days <= step:
        return [(start_date, end_date)]

    return _split_by_fixed_days(start, end, window_days=step, max_segments=max_segments)


def _split_by_fixed_days(
    start: datetime,
    end: datetime,
    *,
    window_days: int,
    max_segments: int,
) -> list[tuple[str, str]]:
    """按固定天数分割。"""
    ranges = []
    current = start
    limit = max(1, int(max_segments))
    required_segments = ((end - start).days + window_days - 1) // window_days
    if required_segments > limit:
        raise ValueError(
            f"微博时间分段数量 {required_segments} 超过安全上限 {limit}，"
            "请缩小时间范围或提高最大分段数"
        )

    while current < end:
        range_end = min(current + timedelta(days=window_days - 1), end)
        ranges.append((current.strftime("%Y-%m-%d"), range_end.strftime("%Y-%m-%d")))
        current = range_end + timedelta(days=1)

    logger.info(f"日期范围按 {window_days} 天分割为 {len(ranges)} 个子范围")
    return ranges
