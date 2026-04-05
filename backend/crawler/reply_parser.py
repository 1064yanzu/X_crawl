"""
TweetDetail 响应解析器

解析 X/Twitter TweetDetail GraphQL API 返回的评论/回复数据。
该 API 的响应结构与 SearchTimeline 不同：
  - data.threaded_conversation_with_injections_v2.instructions[].entries
  - 原推文: entryId 以 "tweet-" 开头，content.__typename == TimelineTimelineItem
  - 回复串: entryId 以 "conversationthread-" 开头，content.__typename == TimelineTimelineModule
  - 分页 cursor: entryId 以 "cursor-" 开头

复用 parser.py 中底层的 _extract_tweet / _extract_user 等工具函数。
"""
import logging
from typing import Optional

# 复用搜索结果解析器中的推文/用户提取方法
from crawler.parser import _extract_tweet, _extract_views

logger = logging.getLogger(__name__)

TWEET_DETAIL_PATTERN = "TweetDetail"


def parse_tweet_detail_response(
    raw_json: dict,
    focal_tweet_id: Optional[str] = None,
) -> tuple[Optional[dict], list[dict], Optional[str], Optional[str], bool]:
    """
    解析 TweetDetail GraphQL 响应。

    Returns:
        (focal_tweet, replies, bottom_cursor, top_cursor, has_spam_boundary)
        focal_tweet:        原始焦点推文（第一条，entryType=TimelineTimelineItem）
        replies:            解析后的回复列表（每个元素是 tweet dict，含 thread_context）
        bottom_cursor:      下一页评论的 cursor
        top_cursor:         上一页评论的 cursor
        has_spam_boundary:  是否遇到 ShowMoreThreads（"显示可能的垃圾信息"）边界，
                            出现时表示有效评论已加载完毕，无需继续翻页
    """
    focal_tweet: Optional[dict] = None
    replies: list[dict] = []
    bottom_cursor: Optional[str] = None
    top_cursor: Optional[str] = None
    has_spam_boundary: bool = False

    try:
        instructions = (
            raw_json
            .get("data", {})
            .get("threaded_conversation_with_injections_v2", {})
            .get("instructions", [])
        )
    except AttributeError:
        logger.error("TweetDetail 响应 JSON 结构异常")
        return focal_tweet, replies, bottom_cursor, top_cursor, has_spam_boundary

    for instruction in instructions:
        entries = instruction.get("entries", [])
        for entry in entries:
            entry_id: str = entry.get("entryId", "")
            content = entry.get("content", {})
            typename = content.get("__typename", "")

            # ── 原推文（焦点帖子）──────────────────────────────────────
            if typename == "TimelineTimelineItem":
                tweet = _parse_detail_item(content)
                if tweet:
                    # 第一条或与 focal_tweet_id 匹配的推文作为焦点推文
                    if focal_tweet is None or (focal_tweet_id and tweet.get("id") == focal_tweet_id):
                        focal_tweet = tweet

            # ── 评论串（Timeline Module）────────────────────────────────
            elif typename == "TimelineTimelineModule":
                thread_replies = _parse_conversation_thread(content)
                replies.extend(thread_replies)

            # ── 分页 Cursor ─────────────────────────────────────────────
            elif typename == "TimelineTimelineCursor":
                cursor_type = content.get("cursorType", "")
                cursor_val = content.get("value")
                if cursor_type == "Bottom" and cursor_val:
                    bottom_cursor = cursor_val
                elif cursor_type == "Top" and cursor_val:
                    top_cursor = cursor_val
                elif cursor_type == "ShowMoreThreads":
                    # 出现"显示可能的垃圾信息"边界，有效评论已加载完毕
                    has_spam_boundary = True
                    logger.debug(
                        f"TweetDetail 检测到 ShowMoreThreads cursor（垃圾信息边界），"
                        f"entryId={entry_id}"
                    )

            # ── 通过 entryId 兜底检测垃圾信息边界 ──────────────────────
            # X API 有时把 ShowMoreThreads 封装在 Module 或其他类型里
            if not has_spam_boundary and (
                "show-more-threads" in entry_id.lower()
                or "show_more_threads" in entry_id.lower()
                or "showmorethreads" in entry_id.lower()
            ):
                has_spam_boundary = True
                logger.debug(
                    f"TweetDetail 通过 entryId 检测到垃圾信息边界，"
                    f"entryId={entry_id}"
                )

    logger.info(
        f"TweetDetail 解析完成：回复 {len(replies)} 条，"
        f"bottomCursor={'有' if bottom_cursor else '无'}"
        f"{'，已到垃圾信息边界' if has_spam_boundary else ''}"
    )
    return focal_tweet, replies, bottom_cursor, top_cursor, has_spam_boundary


# ═══════════════════════════════════════════════════════════════════
#  TimelineItem 解析（原推文）
# ═══════════════════════════════════════════════════════════════════

def _parse_detail_item(content: dict) -> Optional[dict]:
    """解析 TimelineTimelineItem 中的推文（原帖/焦点推文）"""
    item_content = content.get("itemContent", {})
    if item_content.get("__typename") != "TimelineTweet":
        return None

    tweet_result = item_content.get("tweet_results", {}).get("result", {})
    if not tweet_result:
        return None

    if tweet_result.get("__typename") == "TweetWithVisibilityResults":
        tweet_result = tweet_result.get("tweet", {})

    return _extract_tweet(tweet_result)


# ═══════════════════════════════════════════════════════════════════
#  TimelineModule 解析（回复串）
# ═══════════════════════════════════════════════════════════════════

def _parse_conversation_thread(content: dict) -> list[dict]:
    """
    解析一个对话串（TimelineTimelineModule），提取所有回复推文。

    一个对话串可能包含：
    - 多条直连回复（items 里多条 TimelineTweet）
    - "ShowMore" 占位项（entryId 含 "show_more"，跳过）
    - cursor（用于展开更多回复，暂存于 thread_more_cursor 字段）

    Returns:
        list of reply tweet dicts, 每个 dict 带有 thread_context 字段
    """
    items = content.get("items", [])
    result: list[dict] = []

    # 从 metadata 里拿对话所有推文 ID（可辅助构建树形结构）
    meta = content.get("metadata", {}).get("conversationMetadata", {})
    all_tweet_ids_in_thread: list[str] = meta.get("allTweetIds", [])

    for item in items:
        entry_id: str = item.get("entryId", "")
        item_content = item.get("item", {}).get("itemContent", {})
        typename = item_content.get("__typename", "")

        # 跳过广告
        if item_content.get("promotedMetadata"):
            continue

        if typename == "TimelineTweet":
            tweet_result = item_content.get("tweet_results", {}).get("result", {})
            if not tweet_result:
                continue
            if tweet_result.get("__typename") == "TweetWithVisibilityResults":
                tweet_result = tweet_result.get("tweet", {})

            tweet = _extract_tweet(tweet_result)
            if tweet:
                # 附加上下文信息：该回复所在串的所有推文 ID，方便构建树形
                tweet["thread_context"] = {
                    "thread_tweet_ids": all_tweet_ids_in_thread,
                    "position_in_thread": len(result),  # 在本串中的位置
                }
                result.append(tweet)

        elif typename == "TimelineTimelineCursor":
            # 串内 "更多回复" cursor，附加到已有推文上（如果有的话）
            cursor_type = item_content.get("cursorType", "")
            cursor_val = item_content.get("value", "")
            if cursor_type == "Bottom" and cursor_val and result:
                result[-1]["thread_more_cursor"] = cursor_val

    return result
