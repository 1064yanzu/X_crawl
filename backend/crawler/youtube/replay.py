"""
从 raw_responses/{task_id}/youtube/ 下的原始 API 响应重建 YouTube 任务数据。

触发场景：
- 历史任务因旧 `merge_video_detail` bug 把 tweet 精简成 11 字段、丢掉了 replies；
- 评论抓到一半因异常/中断没来得及写回 DB 的情况；
- 想用新解析器重新生成数据。

策略：
- videos：合并 search.list / playlistItems.list 里的 videoId 与 videos.list 的完整详情
- replies：按 video_id 聚合所有 commentThreads.list + comments.list（楼中楼）响应
- 只生成字典，不碰 DB；调用方决定是否把结果写回。
"""
from __future__ import annotations

import logging
from typing import Optional

from crawler.response_saver import iter_youtube_responses
from . import parser

logger = logging.getLogger(__name__)


def rebuild_replies_for_video(task_id: str, video_id: str) -> list[dict]:
    """
    从原始响应重建单个视频的 replies 列表（顶级 + 楼中楼）。

    - commentThreads.list 的 topLevelComment 转为 reply dict
    - 若同一 top-level comment 还有 `comments.list` 的楼中楼响应，则用楼中楼替换内嵌 replies
    - 响应按文件名（含时间戳）排序处理；同一 top_id 重复时后者覆盖前者
    """
    if not task_id or not video_id:
        return []

    # 1) 读所有 commentThreads.list 的顶级评论
    top_by_id: dict[str, dict] = {}
    order: list[str] = []
    for _path, payload in iter_youtube_responses(
        task_id, "commentThreads.list", context=f"video_{video_id}"
    ):
        for thread in payload.get("items") or []:
            reply = parser.comment_thread_to_reply(thread)
            tid = reply.get("id") or ""
            if not tid:
                continue
            if tid not in top_by_id:
                order.append(tid)
            top_by_id[tid] = reply

    if not top_by_id:
        return []

    # 2) 读每个 top_id 对应的 comments.list（楼中楼）响应，覆盖内嵌 replies
    for top_id in list(top_by_id.keys()):
        sub_comments: list[dict] = []
        saw_any = False
        for _path, payload in iter_youtube_responses(
            task_id, "comments.list", context=f"video_{video_id}/parent_{top_id}"
        ):
            saw_any = True
            for comment in payload.get("items") or []:
                sub_comments.append(parser.comment_resource_to_reply(comment))
        if saw_any:
            # 按 comment id 去重，保留最后出现的版本
            dedup: dict[str, dict] = {}
            for c in sub_comments:
                cid = str(c.get("id") or "")
                if cid:
                    dedup[cid] = c
            top_by_id[top_id]["replies"] = list(dedup.values())

    return [top_by_id[tid] for tid in order]


def rebuild_videos(task_id: str) -> list[dict]:
    """
    从 raw_responses 完整重建任务的 videos 列表（含 replies）。
    """
    if not task_id:
        return []

    # 1) 从 videos.list 聚合所有视频详情
    videos_by_id: dict[str, dict] = {}
    order: list[str] = []
    for _path, payload in iter_youtube_responses(task_id, "videos.list"):
        for item in payload.get("items") or []:
            tweet = parser.video_to_tweet(item)
            vid = tweet.get("id")
            if not vid:
                continue
            if vid not in videos_by_id:
                order.append(vid)
                videos_by_id[vid] = tweet
            else:
                # 同一 vid 可能在多批里都返回，保留最后一份（数据最新）
                videos_by_id[vid] = parser.merge_video_detail(videos_by_id[vid], tweet)

    # 2) 若 videos.list 没覆盖所有 id（网络异常/下架），从 search.list / playlistItems.list 补占位
    def _collect_placeholder_ids() -> list[str]:
        ids: list[str] = []
        for endpoint in ("search.list", "playlistItems.list"):
            for _path, payload in iter_youtube_responses(task_id, endpoint):
                for item in payload.get("items") or []:
                    raw_id = item.get("id")
                    if isinstance(raw_id, dict):
                        vid = raw_id.get("videoId")
                    else:
                        content_details = item.get("contentDetails") or {}
                        snippet = item.get("snippet") or {}
                        vid = (
                            content_details.get("videoId")
                            or (snippet.get("resourceId") or {}).get("videoId")
                            or (isinstance(raw_id, str) and raw_id)
                        )
                    vid = str(vid or "").strip()
                    if vid:
                        ids.append(vid)
        return ids

    for vid in _collect_placeholder_ids():
        if vid not in videos_by_id:
            order.append(vid)
            videos_by_id[vid] = {
                "id": vid,
                "platform": "youtube",
                "url": f"https://www.youtube.com/watch?v={vid}",
            }

    # 3) 为每个视频重建 replies
    for vid in order:
        replies = rebuild_replies_for_video(task_id, vid)
        if replies:
            videos_by_id[vid]["replies"] = replies

    return [videos_by_id[vid] for vid in order]


def hydrate_missing_replies(task_id: str, videos: list[dict]) -> tuple[list[dict], int]:
    """
    仅为 `videos` 中 replies 为空/缺失的视频补齐 replies，原视频元数据保持不变。
    返回 (hydrated_videos, replies_recovered_count)。
    """
    if not task_id or not isinstance(videos, list):
        return videos, 0

    recovered = 0
    result: list[dict] = []
    for video in videos:
        if not isinstance(video, dict):
            result.append(video)
            continue
        existing = video.get("replies")
        if isinstance(existing, list) and existing:
            result.append(video)
            continue
        vid = str(video.get("id") or "").strip()
        if not vid:
            result.append(video)
            continue
        replies = rebuild_replies_for_video(task_id, vid)
        if replies:
            updated = dict(video)
            updated["replies"] = replies
            recovered += sum(1 + len(r.get("replies") or []) for r in replies)
            result.append(updated)
        else:
            result.append(video)
    return result, recovered


def has_raw_responses(task_id: Optional[str]) -> bool:
    """快速判断该任务是否存在 YouTube 原始响应目录。"""
    if not task_id:
        return False
    from config import settings, resolve_data_path
    base = resolve_data_path(settings.raw_responses_dir) / task_id / "youtube"
    return base.exists() and any(base.iterdir())
