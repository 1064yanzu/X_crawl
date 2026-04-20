"""
YouTube Data API v3 配额估算。

官方配额规则（详见 docs/YouTube api 文档/配额.md）：
- list 操作大多 1 单位（videos.list、channels.list、playlistItems.list、
  commentThreads.list、comments.list 等）
- search.list 为 100 单位
- insert/update/delete/setModerationStatus 为 50 单位
- captions.insert 400、update 450

仅爬取公开数据时实际用到的：
- search.list           100
- videos.list           1
- channels.list         1
- playlistItems.list    1
- commentThreads.list   1
- comments.list         1

每天默认配额 10000 单位（Pacific Time 00:00 重置）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


# 端点名与官方配额成本一一对应
ENDPOINT_COST: dict[str, int] = {
    "activities.list": 1,
    "captions.list": 50,
    "captions.insert": 400,
    "captions.update": 450,
    "captions.delete": 50,
    "channelBanners.insert": 50,
    "channels.list": 1,
    "channels.update": 50,
    "channelSections.list": 1,
    "channelSections.insert": 50,
    "channelSections.update": 50,
    "channelSections.delete": 50,
    "comments.list": 1,
    "comments.insert": 50,
    "comments.update": 50,
    "comments.setModerationStatus": 50,
    "comments.delete": 50,
    "commentThreads.list": 1,
    "commentThreads.insert": 50,
    "commentThreads.update": 50,
    "guideCategories.list": 1,
    "i18nLanguages.list": 1,
    "i18nRegions.list": 1,
    "members.list": 1,
    "membershipsLevels.list": 1,
    "playlistItems.list": 1,
    "playlistItems.insert": 50,
    "playlistItems.update": 50,
    "playlistItems.delete": 50,
    "playlists.list": 1,
    "playlists.insert": 50,
    "playlists.update": 50,
    "playlists.delete": 50,
    "search.list": 100,
    "subscriptions.list": 1,
    "subscriptions.insert": 50,
    "subscriptions.delete": 50,
    "thumbnails.set": 50,
    "videoAbuseReportReasons.list": 1,
    "videoCategories.list": 1,
    "videos.list": 1,
    "videos.insert": 100,
    "videos.update": 50,
    "videos.rate": 50,
    "videos.reportAbuse": 50,
    "videos.getRating": 1,
    "videos.delete": 50,
    "watermarks.set": 50,
    "watermarks.unset": 50,
}

DAILY_QUOTA_DEFAULT = 10000

# YouTube 配额以太平洋时间计算；使用 UTC-8（冬令时）作为保守估算
_PT_OFFSET_HOURS = -8


def cost_of(endpoint: str) -> int:
    """获取指定端点的配额成本；未知端点按 1 处理（保守）。"""
    return ENDPOINT_COST.get(endpoint, 1)


def estimate_keyword_search_cost(
    *,
    max_videos: int,
    fetch_replies: bool,
    expected_comment_pages_per_video: int = 2,
    reply_depth: int = 1,
) -> dict:
    """
    估算一次关键词搜索任务的总配额消耗。

    拆解：
    - search.list 分页：ceil(max_videos / 50) 次 × 100
    - videos.list 补详情：ceil(max_videos / 50) 次 × 1
    - 评论抓取：max_videos × expected_comment_pages_per_video × 1
    - 楼中楼（depth > 1）：按 1/4 顶级评论被展开估算
    """
    search_pages = max(1, (int(max_videos) + 49) // 50)
    search_cost = search_pages * cost_of("search.list")
    detail_pages = max(1, (int(max_videos) + 49) // 50)
    detail_cost = detail_pages * cost_of("videos.list")

    comment_cost = 0
    if fetch_replies:
        pages = max(1, int(expected_comment_pages_per_video))
        comment_cost = int(max_videos) * pages * cost_of("commentThreads.list")
        if reply_depth and int(reply_depth) > 1:
            comment_cost += int(max_videos) * max(1, pages // 4) * cost_of("comments.list")

    total = search_cost + detail_cost + comment_cost
    return {
        "search_cost": search_cost,
        "detail_cost": detail_cost,
        "comment_cost": comment_cost,
        "total": total,
    }


def estimate_channel_cost(
    *,
    max_videos: int,
    fetch_replies: bool,
    expected_comment_pages_per_video: int = 2,
    reply_depth: int = 1,
) -> dict:
    """
    估算一次频道采集任务的配额消耗。

    - channels.list 1 次
    - playlistItems.list 分页：ceil(max_videos/50) × 1
    - videos.list 补详情：ceil(max_videos/50) × 1
    - 评论：同关键词搜索估算
    """
    playlist_pages = max(1, (int(max_videos) + 49) // 50)
    base_cost = (
        cost_of("channels.list")
        + playlist_pages * cost_of("playlistItems.list")
        + playlist_pages * cost_of("videos.list")
    )

    comment_cost = 0
    if fetch_replies:
        pages = max(1, int(expected_comment_pages_per_video))
        comment_cost = int(max_videos) * pages * cost_of("commentThreads.list")
        if reply_depth and int(reply_depth) > 1:
            comment_cost += int(max_videos) * max(1, pages // 4) * cost_of("comments.list")

    total = base_cost + comment_cost
    return {
        "base_cost": base_cost,
        "comment_cost": comment_cost,
        "total": total,
    }


def compute_next_pt_midnight(now: Optional[datetime] = None) -> datetime:
    """
    计算下一次太平洋时间 00:00 对应的 UTC datetime。

    YouTube 以 Pacific Time 为配额重置基准线。这里用固定 UTC-8 避免依赖
    pytz；相差夏令时 1 小时在配额场景下可忽略（官方文档亦未承诺精确到分钟）。
    """
    now = now or datetime.now(timezone.utc)
    pt_tz = timezone(timedelta(hours=_PT_OFFSET_HOURS))
    pt_now = now.astimezone(pt_tz)
    next_pt_midnight = (pt_now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return next_pt_midnight.astimezone(timezone.utc)
