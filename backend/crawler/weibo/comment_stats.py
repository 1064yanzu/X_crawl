"""
微博评论统计与诊断工具。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CommentTreeStats:
    total_count: int
    top_level_count: int
    max_depth: int


def collect_comment_tree_stats(comments: list[Any]) -> CommentTreeStats:
    total = 0
    max_depth = 0

    def _walk(nodes: list[Any], depth: int) -> None:
        nonlocal total, max_depth
        if not isinstance(nodes, list):
            return
        if nodes:
            max_depth = max(max_depth, depth)
        for node in nodes:
            if not isinstance(node, dict) and not hasattr(node, "to_dict"):
                continue
            total += 1
            replies = _get_replies(node)
            _walk(replies, depth + 1)

    _walk(comments, 1)
    return CommentTreeStats(
        total_count=total,
        top_level_count=len(comments),
        max_depth=max_depth,
    )


def build_comment_stats(
    *,
    post_comment_count: int,
    api_claimed_total: int,
    fetched_total_count: int,
    fetched_top_level_count: int,
    max_depth: int,
    sub_comment_completion_status: str,
    truncated_reason: str | None,
    pages_fetched: int,
) -> dict[str, Any]:
    gap_to_post_meta = max(0, int(post_comment_count or 0) - int(fetched_total_count or 0))
    gap_to_api_claimed = max(0, int(api_claimed_total or 0) - int(fetched_total_count or 0))
    return {
        "post_comment_count": int(post_comment_count or 0),
        "api_claimed_total": int(api_claimed_total or 0),
        "fetched_total_count": int(fetched_total_count or 0),
        "fetched_top_level_count": int(fetched_top_level_count or 0),
        "gap_to_post_meta": gap_to_post_meta,
        "gap_to_api_claimed": gap_to_api_claimed,
        "max_depth": int(max_depth or 0),
        "sub_comment_completion_status": sub_comment_completion_status,
        "truncated_reason": truncated_reason,
        "pages_fetched": int(pages_fetched or 0),
    }


def _get_replies(node: Any) -> list[Any]:
    if isinstance(node, dict):
        replies = node.get("replies")
        return replies if isinstance(replies, list) else []
    replies = getattr(node, "sub_comments", [])
    return replies if isinstance(replies, list) else []
