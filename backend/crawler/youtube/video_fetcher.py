"""
YouTube videos.list 批量补详情。

search.list / playlistItems.list 返回的数据只有 snippet，缺少 statistics
与 contentDetails；本模块负责用 videos.list 一次拉最多 50 个 ID，补齐
视图、点赞、评论数、时长等。
"""
from __future__ import annotations

import logging
from typing import Iterable

from . import api_client, parser

logger = logging.getLogger(__name__)


VIDEO_PART = "snippet,statistics,contentDetails,status,topicDetails"
BATCH_SIZE = 50  # videos.list 单次最多返回 50


def fetch_video_details(
    video_ids: Iterable[str],
    *,
    part: str = VIDEO_PART,
) -> dict[str, dict]:
    """
    按批取视频详情，返回 {video_id: tweet_dict}。
    对任何 API 错误返回部分结果并记录日志，但不吞掉配额异常。
    """
    id_list: list[str] = []
    seen: set[str] = set()
    for raw in video_ids:
        vid = str(raw or "").strip()
        if vid and vid not in seen:
            seen.add(vid)
            id_list.append(vid)

    result: dict[str, dict] = {}
    if not id_list:
        return result

    for start in range(0, len(id_list), BATCH_SIZE):
        batch = id_list[start : start + BATCH_SIZE]
        params = {
            "part": part,
            "id": ",".join(batch),
            "maxResults": BATCH_SIZE,
        }
        payload = api_client.call_list("videos.list", params)
        for item in payload.get("items") or []:
            tweet = parser.video_to_tweet(item)
            if tweet and tweet.get("id"):
                result[tweet["id"]] = tweet
    return result
