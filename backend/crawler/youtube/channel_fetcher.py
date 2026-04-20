"""
YouTube 频道视频列表抓取。

支持两种输入：
- 频道 ID（以 UC 开头）
- 频道用户名 @handle（如 @GoogleDevelopers 或包含完整 URL）

流程：
1. channels.list(part=contentDetails) 拿到 `uploads` playlist ID
2. playlistItems.list 分页拉取该 playlist
3. 返回 video_id 序列，交由上层用 video_fetcher 补齐详情
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

from . import api_client

logger = logging.getLogger(__name__)

_URL_HANDLE_RE = re.compile(r"youtube\.com/@([^/?&#]+)", re.IGNORECASE)
_URL_CHANNEL_ID_RE = re.compile(r"youtube\.com/channel/([^/?&#]+)", re.IGNORECASE)
_URL_CUSTOM_RE = re.compile(r"youtube\.com/(?:c|user)/([^/?&#]+)", re.IGNORECASE)


def normalize_channel_input(raw: str) -> dict:
    """
    归一化用户输入的频道描述符。
    返回 {"kind": "id"|"handle"|"username", "value": "..."}。
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("频道标识不能为空")

    # 直接 URL
    match = _URL_CHANNEL_ID_RE.search(text)
    if match:
        return {"kind": "id", "value": match.group(1)}
    match = _URL_HANDLE_RE.search(text)
    if match:
        handle = match.group(1)
        return {"kind": "handle", "value": f"@{handle}"}
    match = _URL_CUSTOM_RE.search(text)
    if match:
        return {"kind": "username", "value": match.group(1)}

    # 原始 @handle
    if text.startswith("@"):
        return {"kind": "handle", "value": text}

    # 看起来像 channelId（UC 开头、24 位）
    if text.startswith("UC") and len(text) >= 20:
        return {"kind": "id", "value": text}

    # 默认当 username
    return {"kind": "username", "value": text}


def resolve_uploads_playlist(channel_input: str) -> dict:
    """
    把用户输入解析为 channel_id + uploads_playlist_id。
    返回 {"channel_id": ..., "uploads_playlist_id": ..., "channel_title": ..., "channel_info": {...}}
    """
    descriptor = normalize_channel_input(channel_input)
    params = {"part": "snippet,contentDetails,statistics"}
    if descriptor["kind"] == "id":
        params["id"] = descriptor["value"]
    elif descriptor["kind"] == "handle":
        params["forHandle"] = descriptor["value"]
    else:
        params["forUsername"] = descriptor["value"]

    payload = api_client.call_list("channels.list", params)
    items = payload.get("items") or []
    if not items:
        raise ValueError(f"未找到频道: {channel_input}")

    channel = items[0]
    snippet = channel.get("snippet") or {}
    content = channel.get("contentDetails") or {}
    related = content.get("relatedPlaylists") or {}
    uploads_playlist_id = related.get("uploads")
    if not uploads_playlist_id:
        raise ValueError(f"频道未提供 uploads 播放列表: {channel_input}")
    return {
        "channel_id": channel.get("id"),
        "uploads_playlist_id": uploads_playlist_id,
        "channel_title": snippet.get("title"),
        "channel_info": channel,
    }


def iter_playlist_video_ids(
    uploads_playlist_id: str,
    *,
    max_videos: int,
    start_page_token: Optional[str] = None,
):
    """
    生成 (page_index, video_ids_this_page, next_page_token, raw_items)
    直到满足 max_videos 或没有下一页。
    """
    collected = 0
    next_token = start_page_token
    page_index = 0
    while True:
        remaining = max_videos - collected
        if remaining <= 0:
            return
        params = {
            "part": "snippet,contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": min(50, remaining),
        }
        if next_token:
            params["pageToken"] = next_token

        payload = api_client.call_list("playlistItems.list", params)
        items = payload.get("items") or []
        video_ids: list[str] = []
        for item in items:
            content = item.get("contentDetails") or {}
            snippet = item.get("snippet") or {}
            vid = content.get("videoId") or (snippet.get("resourceId") or {}).get("videoId")
            if vid:
                video_ids.append(str(vid))

        next_token = payload.get("nextPageToken")
        collected += len(video_ids)
        yield page_index, video_ids, next_token, items
        page_index += 1

        if not next_token:
            return
        if collected >= max_videos:
            return
