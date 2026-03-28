"""
GraphQL 响应完整解析模块（工业级）
基于真实抓包 JSON 提取所有可用字段：
- 推文完整字段（source、conversation_id、reply_to、possibly_sensitive 等）
- 用户完整字段（website、profile_description_language、listed_count 等）
- 媒体完整字段（所有视频清晰度变体、视频时长、纵横比、MIME 格式）
- 被引用的原推文（quoted_tweet）
- 被转推的原推文（retweeted_tweet）
- @提及用户列表（user_mentions）
- 高亮关键词位置（text_highlights）
- 翻页 cursor（Bottom / Top）
- 兼容 TimelineReplaceEntry / TimelineTimelineModule 等新式结构
"""
import logging
import re
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  顶层入口
# ═══════════════════════════════════════════════════════════════════

def parse_search_response(raw_json: dict) -> tuple[list[dict], Optional[str], Optional[str]]:
    """
    解析 SearchTimeline GraphQL 响应

    Returns:
        (tweets, bottom_cursor, top_cursor)
        tweets:        规范化推文列表
        bottom_cursor: 下一页 cursor（None 表示无更多数据）
        top_cursor:    上一页 cursor（用于向前翻页）
    """
    tweets: list[dict] = []
    bottom_cursor: Optional[str] = None
    top_cursor: Optional[str] = None

    try:
        instructions = (
            raw_json
            .get("data", {})
            .get("search_by_raw_query", {})
            .get("search_timeline", {})
            .get("timeline", {})
            .get("instructions", [])
        )
    except AttributeError:
        logger.error("响应 JSON 结构异常，无法解析 instructions")
        return tweets, bottom_cursor, top_cursor

    for instruction in instructions:
        for entry in _iter_instruction_entries(instruction):
            entry_tweets, entry_bottom_cursor, entry_top_cursor = _parse_timeline_entry(entry)
            if entry_tweets:
                tweets.extend(entry_tweets)
            if entry_bottom_cursor:
                bottom_cursor = entry_bottom_cursor
            if entry_top_cursor:
                top_cursor = entry_top_cursor

    logger.info(
        f"解析完成：{len(tweets)} 条推文，"
        f"bottomCursor={'有' if bottom_cursor else '无'}，"
        f"topCursor={'有' if top_cursor else '无'}"
    )
    return tweets, bottom_cursor, top_cursor


# ═══════════════════════════════════════════════════════════════════
#  TimelineItem 解析
# ═══════════════════════════════════════════════════════════════════

def _parse_timeline_item(content: dict) -> Optional[dict]:
    return _parse_timeline_item_content(content.get("itemContent", {}))


def _parse_timeline_item_content(item_content: dict) -> Optional[dict]:
    if item_content.get("__typename") != "TimelineTweet":
        return None

    tweet_result = item_content.get("tweet_results", {}).get("result", {})
    if not tweet_result:
        return None

    # TweetWithVisibilityResults 包装
    if tweet_result.get("__typename") == "TweetWithVisibilityResults":
        tweet_result = tweet_result.get("tweet", {})

    # 关键词高亮位置（搜索结果中的匹配区间）
    highlights = [
        {"start": h.get("startIndex"), "end": h.get("endIndex")}
        for h in (
            item_content.get("highlights", {}).get("textHighlights", [])
        )
    ]

    tweet = _extract_tweet(tweet_result)
    if tweet and highlights:
        tweet["text_highlights"] = highlights
    return tweet


def _iter_instruction_entries(instruction: dict) -> list[dict]:
    """兼容 TimelineAddEntries / TimelineReplaceEntry 两种 instruction 结构。"""
    entries: list[dict] = []

    raw_entries = instruction.get("entries", [])
    if isinstance(raw_entries, list):
        entries.extend(entry for entry in raw_entries if isinstance(entry, dict))

    raw_entry = instruction.get("entry")
    if isinstance(raw_entry, dict):
        entries.append(raw_entry)

    return entries


def _parse_timeline_entry(entry: dict) -> tuple[list[dict], Optional[str], Optional[str]]:
    """解析单个 timeline entry。"""
    content = entry.get("content", {})
    typename = content.get("__typename", "")

    if typename == "TimelineTimelineItem":
        tweet = _parse_timeline_item(content)
        return ([tweet] if tweet else []), None, None

    if typename == "TimelineTimelineModule":
        return _parse_timeline_module(content), None, None

    if typename == "TimelineTimelineCursor":
        return [], *_extract_cursor(content)

    return [], None, None


def _parse_timeline_module(content: dict) -> list[dict]:
    """兼容搜索页中以 module 形式返回的推文列表。"""
    tweets: list[dict] = []
    for item in content.get("items", []):
        if not isinstance(item, dict):
            continue
        item_node = item.get("item", {}) if isinstance(item.get("item"), dict) else {}
        item_content = item_node.get("itemContent") or item.get("itemContent") or {}
        if not isinstance(item_content, dict):
            continue
        tweet = _parse_timeline_item_content(item_content)
        if tweet:
            tweets.append(tweet)
    return tweets


def _extract_cursor(content: dict) -> tuple[Optional[str], Optional[str]]:
    cursor_type = content.get("cursorType", "")
    cursor_val = content.get("value")
    if cursor_type == "Bottom" and cursor_val:
        return cursor_val, None
    if cursor_type == "Top" and cursor_val:
        return None, cursor_val
    return None, None


# ═══════════════════════════════════════════════════════════════════
#  推文提取
# ═══════════════════════════════════════════════════════════════════

def _extract_tweet(tweet_result: dict, depth: int = 0) -> Optional[dict]:
    """递归提取推文（depth 限制防止无限递归）"""
    if depth > 2:
        return None
    if tweet_result.get("__typename") not in ("Tweet", None, ""):
        # 某些情况下 __typename 可能缺失，宽松处理
        if tweet_result.get("__typename") and tweet_result["__typename"] != "Tweet":
            return None

    legacy = tweet_result.get("legacy", {})
    if not legacy:
        return None

    # ──────────── 基础字段 ────────────
    tweet_id = legacy.get("id_str") or tweet_result.get("rest_id", "")
    conversation_id = legacy.get("conversation_id_str", "")

    # 回复对象（in_reply_to）
    reply_to_tweet_id = legacy.get("in_reply_to_status_id_str")
    reply_to_user_id = legacy.get("in_reply_to_user_id_str")
    reply_to_screen_name = legacy.get("in_reply_to_screen_name")

    # 发推客户端来源（strip HTML tags）
    source_raw = tweet_result.get("source", "")
    source = _strip_html(source_raw)

    # 作者
    author_result = (
        tweet_result.get("core", {})
        .get("user_results", {})
        .get("result", {})
    )
    author = _extract_user(author_result)

    screen_name = author.get("screen_name", "") if author else ""
    tweet_url = (
        f"https://x.com/{screen_name}/status/{tweet_id}"
        if screen_name and tweet_id else ""
    )

    # ──────────── 媒体 ────────────
    media_list = _extract_media(legacy)

    # ──────────── entities ────────────
    entities = legacy.get("entities", {})
    hashtags = [h.get("text", "") for h in entities.get("hashtags", [])]
    symbols = [s.get("text", "") for s in entities.get("symbols", [])]
    urls = [
        {
            "url": u.get("url"),
            "expanded_url": u.get("expanded_url"),
            "display_url": u.get("display_url"),
            "title": u.get("title"),  # 某些链接预览有 title
        }
        for u in entities.get("urls", [])
    ]
    user_mentions = [
        {
            "id": m.get("id_str"),
            "name": m.get("name"),
            "screen_name": m.get("screen_name"),
        }
        for m in entities.get("user_mentions", [])
    ]

    # ──────────── 创建时间 ────────────
    created_at_iso = _parse_twitter_date(legacy.get("created_at", ""))

    # ──────────── 可编辑性 ────────────
    edit_control = tweet_result.get("edit_control", {})
    is_edit_eligible = edit_control.get("is_edit_eligible", False)
    edits_remaining = _safe_int(edit_control.get("edits_remaining"))
    editable_until = _safe_int_to_iso(edit_control.get("editable_until_msecs"))

    # ──────────── 被引用原推文 ────────────
    quoted_tweet = None
    quoted_result = tweet_result.get("quoted_status_result", {}).get("result", {})
    if quoted_result:
        if quoted_result.get("__typename") == "TweetWithVisibilityResults":
            quoted_result = quoted_result.get("tweet", {})
        quoted_tweet = _extract_tweet(quoted_result, depth=depth + 1)

    # ──────────── 被转推的原推文 ────────────
    retweeted_tweet = None
    rt_result = (
        legacy.get("retweeted_status_result", {})
        or tweet_result.get("retweeted_status_result", {})
    )
    if rt_result:
        rt_inner = rt_result.get("result", {})
        if rt_inner.get("__typename") == "TweetWithVisibilityResults":
            rt_inner = rt_inner.get("tweet", {})
        retweeted_tweet = _extract_tweet(rt_inner, depth=depth + 1)

    return {
        # ── 推文基础 ──
        "id": tweet_id,
        "conversation_id": conversation_id,
        "text": legacy.get("full_text", ""),
        "display_text_range": legacy.get("display_text_range"),
        "created_at": created_at_iso,
        "lang": legacy.get("lang", ""),
        "url": tweet_url,
        "source": source,                       # 发推客户端
        "possibly_sensitive": legacy.get("possibly_sensitive", False),
        "is_translatable": tweet_result.get("is_translatable", False),
        # ── 回复信息 ──
        "reply_to": {
            "tweet_id": reply_to_tweet_id,
            "user_id": reply_to_user_id,
            "screen_name": reply_to_screen_name,
        } if reply_to_tweet_id else None,
        # ── 互动指标 ──
        "metrics": {
            "likes": legacy.get("favorite_count", 0),
            "retweets": legacy.get("retweet_count", 0),
            "replies": legacy.get("reply_count", 0),
            "quotes": legacy.get("quote_count", 0),
            "bookmarks": legacy.get("bookmark_count", 0),
            "views": _extract_views(tweet_result),
            "views_state": tweet_result.get("views", {}).get("state"),
        },
        # ── 作者 ──
        "author": author,
        # ── 媒体 ──
        "media": media_list,
        # ── 文本实体 ──
        "hashtags": hashtags,
        "symbols": symbols,
        "urls": urls,
        "user_mentions": user_mentions,
        # ── 推文类型 ──
        "is_retweet": bool(retweeted_tweet),
        "is_quote": legacy.get("is_quote_status", False),
        # ── 关联推文 ──
        "quoted_tweet": quoted_tweet,
        "retweeted_tweet": retweeted_tweet,
        # ── 可编辑性 ──
        "edit_info": {
            "is_edit_eligible": is_edit_eligible,
            "edits_remaining": edits_remaining,
            "editable_until": editable_until,
        },
        # ── 关键词高亮（由外层设置）──
        "text_highlights": [],
    }


# ═══════════════════════════════════════════════════════════════════
#  用户提取
# ═══════════════════════════════════════════════════════════════════

def _extract_user(user_result: dict) -> Optional[dict]:
    if not user_result:
        return None
    typename = user_result.get("__typename", "")
    if typename and typename != "User":
        return None

    legacy = user_result.get("legacy", {})
    avatar = user_result.get("avatar", {})
    location_obj = user_result.get("location", {})
    verification = user_result.get("verification", {})
    core = user_result.get("core", {})

    # 个人主页链接（从 entities.url.urls 中提取）
    website_url = None
    website_display = None
    url_entities = legacy.get("entities", {}).get("url", {}).get("urls", [])
    if url_entities:
        website_url = url_entities[0].get("expanded_url")
        website_display = url_entities[0].get("display_url")

    # description 中的 @提及 和链接
    desc_entities = legacy.get("entities", {}).get("description", {})
    desc_urls = [
        {
            "url": u.get("url"),
            "expanded_url": u.get("expanded_url"),
            "display_url": u.get("display_url"),
        }
        for u in desc_entities.get("urls", [])
    ]
    desc_mentions = [
        {"screen_name": m.get("screen_name")}
        for m in desc_entities.get("user_mentions", [])
    ]

    return {
        # ── 基础 ──
        "id": user_result.get("rest_id", ""),
        "name": core.get("name") or legacy.get("name", ""),
        "screen_name": core.get("screen_name") or legacy.get("screen_name", ""),
        "description": legacy.get("description", ""),
        "description_language": user_result.get("profile_description_language", ""),
        # ── 图像 ──
        "avatar_url": (
            avatar.get("image_url") or legacy.get("profile_image_url_https", "")
        ).replace("_normal", ""),
        "banner_url": legacy.get("profile_banner_url", ""),
        "profile_image_shape": user_result.get("profile_image_shape", ""),
        # ── 位置 ──
        "location": location_obj.get("location", "") if isinstance(location_obj, dict) else "",
        # ── 主页链接 ──
        "website_url": website_url,
        "website_display": website_display,
        # ── 统计数据 ──
        "followers_count": legacy.get("followers_count", 0),
        "following_count": legacy.get("friends_count", 0),
        "tweets_count": legacy.get("statuses_count", 0),
        "likes_count": legacy.get("favourites_count", 0),
        "media_count": legacy.get("media_count", 0),
        "listed_count": legacy.get("listed_count", 0),
        # ── 认证 ──
        "verified": verification.get("verified", False) if isinstance(verification, dict) else False,
        "verified_type": verification.get("verified_type") if isinstance(verification, dict) else None,
        "is_blue_verified": user_result.get("is_blue_verified", False),
        # ── 账号属性 ──
        "created_at": _parse_twitter_date(core.get("created_at", "") or legacy.get("created_at", "")),
        "is_protected": user_result.get("privacy", {}).get("protected", False),
        "is_translator": legacy.get("is_translator", False),
        "has_custom_timelines": legacy.get("has_custom_timelines", False),
        "pinned_tweet_ids": legacy.get("pinned_tweet_ids_str", []),
        # ── description 实体 ──
        "description_urls": desc_urls,
        "description_mentions": desc_mentions,
    }


# ═══════════════════════════════════════════════════════════════════
#  媒体提取
# ═══════════════════════════════════════════════════════════════════

def _extract_media(legacy: dict) -> list[dict]:
    extended = legacy.get("extended_entities", {})
    media_items = extended.get("media", [])

    # fallback 到普通 entities
    if not media_items:
        media_items = legacy.get("entities", {}).get("media", [])

    result = []
    for media in media_items:
        media_type = media.get("type", "photo")
        orig = media.get("original_info", {})

        item: dict[str, Any] = {
            "id": media.get("id_str", ""),
            "media_key": media.get("media_key", ""),
            "type": media_type,
            "url": media.get("media_url_https", ""),
            "display_url": media.get("display_url", ""),
            "expanded_url": media.get("expanded_url", ""),
            "width": orig.get("width"),
            "height": orig.get("height"),
            "alt_text": media.get("ext_alt_text"),
            "sensitive": media.get("ext_media_availability", {}).get("status") != "Available",
        }

        # 各尺寸变体（thumb/small/medium/large）
        item["sizes"] = {
            size: {
                "w": info.get("w"),
                "h": info.get("h"),
                "resize": info.get("resize"),
            }
            for size, info in media.get("sizes", {}).items()
        }

        if media_type in ("video", "animated_gif"):
            video_info = media.get("video_info", {})
            aspect = video_info.get("aspect_ratio", [])
            duration_ms = video_info.get("duration_millis")

            item["video_info"] = {
                "aspect_ratio": aspect,
                "duration_ms": duration_ms,
                "duration_sec": round(duration_ms / 1000, 2) if duration_ms else None,
            }

            # 所有视频清晰度变体
            variants = video_info.get("variants", [])
            item["video_variants"] = [
                {
                    "bitrate": v.get("bitrate"),
                    "content_type": v.get("content_type"),
                    "url": v.get("url"),
                }
                for v in sorted(variants, key=lambda v: v.get("bitrate", 0), reverse=True)
            ]

            # 最优 MP4（最高码率）
            mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
            if mp4s:
                best = max(mp4s, key=lambda v: v.get("bitrate", 0))
                item["video_url"] = best.get("url")
                item["video_bitrate"] = best.get("bitrate")

            # HLS 流
            hls = next((v for v in variants if "mpegURL" in v.get("content_type", "")), None)
            if hls:
                item["hls_url"] = hls.get("url")

        result.append(item)
    return result


# ═══════════════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════════════

def _extract_views(tweet_result: dict) -> Optional[int]:
    try:
        count_str = tweet_result.get("views", {}).get("count")
        return int(count_str) if count_str else None
    except (ValueError, TypeError):
        return None


def _parse_twitter_date(date_str: str) -> str:
    """Twitter 日期格式 → ISO 8601，空字符串返回空字符串"""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")
        return dt.isoformat()
    except ValueError:
        return date_str


def _strip_html(text: str) -> str:
    """去除 HTML 标签，提取纯文本（用于 source 字段）"""
    return re.sub(r"<[^>]+>", "", text).strip()


def _safe_int(val: Any) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _safe_int_to_iso(msecs: Any) -> Optional[str]:
    """毫秒时间戳 → ISO 8601"""
    ms = _safe_int(msecs)
    if ms is None:
        return None
    try:
        from datetime import timezone
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None
