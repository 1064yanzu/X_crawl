"""
日期范围分割器。
用于将大范围日期拆分为多个小范围，以突破微博搜索 50 页限制。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def split_date_range(
    start_date: str,
    end_date: str,
    max_pages: int = 50,
    total_pages_first_query: int = 0,
) -> list[tuple[str, str]]:
    """
    根据日期范围和预估的结果密度，将日期范围分割为多个子范围。

    如果 total_pages_first_query 超过了 max_pages，
    则按月或按天细分以突破结果数量限制。

    Args:
        start_date: 开始日期（YYYY-MM-DD）
        end_date: 结束日期（YYYY-MM-DD）
        max_pages: 单次查询最多页数（微博限制 50 页）
        total_pages_first_query: 首次查询返回的总页数，用于判断是否需要分割

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

    total_days = (end - start).days

    # 如果总天数很小（< 7 天），不分割
    if total_days <= 7:
        return [(start_date, end_date)]

    # 根据首次查询的页数估算密度并决定分割粒度
    if total_pages_first_query > 0 and total_pages_first_query >= max_pages:
        # 数据密度高，需要细分
        #   > 50 页且跨度大 → 按月分割
        #   > 50 页且跨度较小 → 按周分割
        if total_days > 60:
            return _split_by_month(start, end)
        elif total_days > 14:
            return _split_by_weeks(start, end, week_size=7)
        else:
            return _split_by_days(start, end, day_size=3)
    elif total_days > 365:
        # > 1 年，即使首次未超页，也按3月分割以避免潜在截断
        return _split_by_month(start, end, months=3)
    elif total_days > 180:
        # > 半年，按月分割
        return _split_by_month(start, end)
    else:
        # 无需分割
        return [(start_date, end_date)]


def _split_by_month(
    start: datetime, end: datetime, months: int = 1
) -> list[tuple[str, str]]:
    """按月分割日期范围。"""
    ranges = []
    current = start
    while current < end:
        # 计算当月末尾
        month_end = current
        for _ in range(months):
            # 跳到下个月的第一天
            if month_end.month == 12:
                month_end = month_end.replace(year=month_end.year + 1, month=1, day=1)
            else:
                month_end = month_end.replace(month=month_end.month + 1, day=1)
        # 回退一天得到当月最后一天
        month_end = month_end - timedelta(days=1)

        range_end = min(month_end, end)
        ranges.append((current.strftime("%Y-%m-%d"), range_end.strftime("%Y-%m-%d")))
        current = range_end + timedelta(days=1)

    logger.info(f"日期范围按月分割为 {len(ranges)} 个子范围")
    return ranges


def _split_by_weeks(
    start: datetime, end: datetime, week_size: int = 7
) -> list[tuple[str, str]]:
    """按固定天数分割。"""
    ranges = []
    current = start
    while current < end:
        range_end = min(current + timedelta(days=week_size - 1), end)
        ranges.append((current.strftime("%Y-%m-%d"), range_end.strftime("%Y-%m-%d")))
        current = range_end + timedelta(days=1)

    logger.info(f"日期范围按 {week_size} 天分割为 {len(ranges)} 个子范围")
    return ranges


def _split_by_days(
    start: datetime, end: datetime, day_size: int = 3
) -> list[tuple[str, str]]:
    """按几天一个范围分割。"""
    return _split_by_weeks(start, end, week_size=day_size)
