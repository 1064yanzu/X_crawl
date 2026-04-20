"""
YouTube API 响应 → 统一 tweet/reply dict 解析器。

设计目标：
- 复用项目已有的 TweetOut / UserOut / reply 结构，避免前端大改
- YouTube 专属字段（时长、分类、直播标记等）放到顶层 `platform_extra`
- 所有字段都做 str/int 转换以保证 JSON 序列化安全
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


_ISO_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def parse_iso_duration(iso: Optional[str]) -> Optional[int]:
    """将 ISO 8601 duration（PT#H#M#S）转为秒；无法解析时返回 None。"""
    if not iso:
        return None
    match = _ISO_DURATION_RE.match(str(iso))
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else 0


def pick_thumbnail(thumbnails: Optional[dict]) -> dict:
    """从 thumbnails 字典中选取尽可能高清的一张。"""
    if not isinstance(thumbnails, dict) or not thumbnails:
        return {}
    for size in ("maxres", "standard", "high", "medium", "default"):
        thumb = thumbnails.get(size)
        if isinstance(thumb, dict) and thumb.get("url"):
            return {
                "size": size,
                "url": thumb.get("url"),
                "width": thumb.get("width"),
                "height": thumb.get("height"),
            }
    return {}


def _author_from_video_snippet(snippet: dict) -> dict:
    return {
        "id": _as_str(snippet.get("channelId")),
        "name": _as_str(snippet.get("channelTitle")),
        "screen_name": _as_str(snippet.get("channelTitle")),
        "description": "",
        "avatar_url": "",
        "banner_url": "",
        "location": "",
        "followers_count": 0,
        "following_count": 0,
        "tweets_count": 0,
        "verified": False,
        "verified_type": None,
        "is_blue_verified": False,
        "professional_type": None,
        "professional_category": None,
        "affiliate_label": None,
        "verified_type_num": -1,
        "verified_type_str": "",
        "verified_reason": "",
        "mbtype": 0,
        "mbrank": 0,
        "created_at": None,
    }


def video_to_tweet(video: dict) -> dict:
    """
    `video` 是 videos.list / search.list / playlistItems 响应中的单条记录。
    search.list 的 id 字段为 `{videoId: ...}`；videos.list 的 id 为字符串。
    """
    if not isinstance(video, dict):
        return {}

    raw_id = video.get("id")
    if isinstance(raw_id, dict):
        video_id = _as_str(raw_id.get("videoId") or raw_id.get("video_id"))
    else:
        video_id = _as_str(raw_id)
    if not video_id:
        content_details = video.get("contentDetails") or {}
        video_id = _as_str(content_details.get("videoId"))

    snippet = video.get("snippet") or {}
    statistics = video.get("statistics") or {}
    content_details = video.get("contentDetails") or {}
    status_block = video.get("status") or {}
    topic_details = video.get("topicDetails") or {}

    title = _as_str(snippet.get("title"))
    description = _as_str(snippet.get("description"))
    text_parts = [title]
    if description:
        text_parts.append("")
        text_parts.append(description)
    text = "\n".join(text_parts).strip()

    thumb = pick_thumbnail(snippet.get("thumbnails"))
    media_item: dict = {}
    if thumb:
        media_item = {
            "id": video_id,
            "media_key": thumb.get("url", ""),
            "type": "video",
            "url": thumb.get("url", ""),
            "display_url": f"youtu.be/{video_id}",
            "expanded_url": f"https://www.youtube.com/watch?v={video_id}",
            "width": thumb.get("width"),
            "height": thumb.get("height"),
            "alt_text": title,
            "sensitive": False,
            "sizes": {},
            "video_info": None,
            "video_variants": [],
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "video_bitrate": None,
            "hls_url": None,
        }

    view_count = _as_int(statistics.get("viewCount"))
    like_count = _as_int(statistics.get("likeCount"))
    comment_count = _as_int(statistics.get("commentCount"))

    duration_sec = parse_iso_duration(content_details.get("duration"))

    tweet = {
        "id": video_id,
        "conversation_id": video_id,
        "text": text,
        "display_text_range": None,
        "created_at": _as_str(snippet.get("publishedAt")),
        "lang": _as_str(snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage")),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "source": "",
        "possibly_sensitive": False,
        "is_translatable": False,
        "reply_to": None,
        "metrics": {
            "likes": like_count,
            "retweets": 0,
            "replies": comment_count,
            "quotes": 0,
            "bookmarks": 0,
            "views": view_count,
            "views_state": "EnabledWithCount" if view_count else None,
        },
        "author": _author_from_video_snippet(snippet),
        "media": [media_item] if media_item else [],
        "hashtags": list(snippet.get("tags") or []),
        "symbols": [],
        "urls": [],
        "user_mentions": [],
        "is_retweet": False,
        "is_quote": False,
        "quoted_tweet": None,
        "retweeted_tweet": None,
        "edit_info": None,
        "text_highlights": [],
        "replies": [],
        "thread_context": None,
        "thread_more_cursor": None,
        # YouTube 专属扩展
        "platform": "youtube",
        "platform_extra": {
            "video_id": video_id,
            "title": title,
            "description": description,
            "channel_id": _as_str(snippet.get("channelId")),
            "channel_title": _as_str(snippet.get("channelTitle")),
            "category_id": _as_str(snippet.get("categoryId")),
            "duration_iso": _as_str(content_details.get("duration")),
            "duration_sec": duration_sec,
            "definition": _as_str(content_details.get("definition")),
            "dimension": _as_str(content_details.get("dimension")),
            "licensed_content": bool(content_details.get("licensedContent")),
            "caption": _as_str(content_details.get("caption")),
            "projection": _as_str(content_details.get("projection")),
            "live_broadcast_content": _as_str(snippet.get("liveBroadcastContent")),
            "privacy_status": _as_str(status_block.get("privacyStatus")),
            "upload_status": _as_str(status_block.get("uploadStatus")),
            "embeddable": bool(status_block.get("embeddable", True)),
            "topic_categories": list(topic_details.get("topicCategories") or []),
            "thumbnail": thumb,
            "tags": list(snippet.get("tags") or []),
            "default_language": _as_str(snippet.get("defaultLanguage")),
            "default_audio_language": _as_str(snippet.get("defaultAudioLanguage")),
            "favorite_count": _as_int(statistics.get("favoriteCount")),
            "dislike_count": _as_int(statistics.get("dislikeCount")),
            # search.list 的 publishedAt 与 videos.list 的 publishedAt 都映射到 created_at
        },
    }
    return tweet


def merge_video_detail(existing: dict, detailed: dict) -> dict:
    """
    使用 videos.list 的完整数据更新 search.list 返回的轻量快照。
    """
    if not existing:
        return detailed
    if not detailed:
        return existing

    merged = dict(existing)
    merged["text"] = detailed.get("text") or merged.get("text", "")
    merged["lang"] = detailed.get("lang") or merged.get("lang", "")
    merged["created_at"] = detailed.get("created_at") or merged.get("created_at", "")

    if detailed.get("metrics"):
        merged.setdefault("metrics", {})
        merged["metrics"] = {**merged["metrics"], **detailed["metrics"]}

    if detailed.get("media"):
        merged["media"] = detailed["media"]
    if detailed.get("author"):
        merged["author"] = detailed["author"]
    if detailed.get("hashtags"):
        merged["hashtags"] = detailed["hashtags"]
    if detailed.get("platform_extra"):
        merged.setdefault("platform_extra", {})
        merged["platform_extra"] = {
            **merged.get("platform_extra", {}),
            **detailed.get("platform_extra", {}),
        }
    return merged


# ── 评论解析 ────────────────────────────────────────────────────────────────


def _author_from_comment_snippet(snippet: dict) -> dict:
    channel_id = ""
    author_ch = snippet.get("authorChannelId") or {}
    if isinstance(author_ch, dict):
        channel_id = _as_str(author_ch.get("value"))
    return {
        "id": channel_id,
        "name": _as_str(snippet.get("authorDisplayName")),
        "screen_name": _as_str(snippet.get("authorDisplayName")),
        "description": "",
        "avatar_url": _as_str(snippet.get("authorProfileImageUrl")),
        "banner_url": "",
        "location": "",
        "followers_count": 0,
        "following_count": 0,
        "tweets_count": 0,
        "verified": False,
        "verified_type": None,
        "is_blue_verified": False,
        "professional_type": None,
        "professional_category": None,
        "affiliate_label": None,
        "verified_type_num": -1,
        "verified_type_str": "",
        "verified_reason": "",
        "mbtype": 0,
        "mbrank": 0,
        "created_at": None,
    }


def _comment_resource_to_reply(comment: dict, *, total_reply_count: int = 0) -> dict:
    snippet = comment.get("snippet") or {}
    comment_id = _as_str(comment.get("id"))
    like_count = _as_int(snippet.get("likeCount"))
    return {
        "id": comment_id,
        "conversation_id": _as_str(snippet.get("videoId")) or comment_id,
        "text": _as_str(snippet.get("textDisplay")),
        "display_text_range": None,
        "created_at": _as_str(snippet.get("publishedAt")),
        "lang": "",
        "url": (
            f"https://www.youtube.com/watch?v={_as_str(snippet.get('videoId'))}"
            f"&lc={comment_id}"
        ) if snippet.get("videoId") else "",
        "source": "",
        "possibly_sensitive": False,
        "is_translatable": False,
        "reply_to": None,
        "metrics": {
            "likes": like_count,
            "retweets": 0,
            "replies": int(total_reply_count or 0),
            "quotes": 0,
            "bookmarks": 0,
            "views": None,
            "views_state": None,
        },
        "author": _author_from_comment_snippet(snippet),
        "media": [],
        "hashtags": [],
        "symbols": [],
        "urls": [],
        "user_mentions": [],
        "is_retweet": False,
        "is_quote": False,
        "quoted_tweet": None,
        "retweeted_tweet": None,
        "edit_info": None,
        "text_highlights": [],
        "replies": [],
        "thread_context": None,
        "thread_more_cursor": None,
        "platform": "youtube",
        "platform_extra": {
            "comment_id": comment_id,
            "author_channel_id": _author_from_comment_snippet(snippet).get("id"),
            "parent_id": _as_str(snippet.get("parentId")),
            "text_original": _as_str(snippet.get("textOriginal")),
            "updated_at": _as_str(snippet.get("updatedAt")),
            "can_rate": bool(snippet.get("canRate", False)),
            "viewer_rating": _as_str(snippet.get("viewerRating")),
            "moderation_status": _as_str(snippet.get("moderationStatus")),
        },
    }


def comment_thread_to_reply(thread: dict) -> dict:
    """
    `commentThreads.list` 返回的每条记录 → 统一 reply dict。
    若包含 `replies.comments`，按时间顺序附加为二级 replies。
    """
    if not isinstance(thread, dict):
        return {}
    snippet = thread.get("snippet") or {}
    top_comment = (snippet.get("topLevelComment") or {})
    total_reply_count = _as_int(snippet.get("totalReplyCount"))
    reply_dict = _comment_resource_to_reply(top_comment, total_reply_count=total_reply_count)

    embedded = thread.get("replies") or {}
    embedded_comments = embedded.get("comments") if isinstance(embedded, dict) else []
    if embedded_comments:
        reply_dict["replies"] = [
            _comment_resource_to_reply(c) for c in embedded_comments
        ]
    return reply_dict


def comment_resource_to_reply(comment: dict) -> dict:
    """直接把 `comments.list` 返回的 comment 资源转为 reply dict。"""
    return _comment_resource_to_reply(comment)
