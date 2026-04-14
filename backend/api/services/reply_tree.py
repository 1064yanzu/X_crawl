"""评论树统计工具。"""
from __future__ import annotations

from typing import Any


def count_reply_tree_nodes(replies: object) -> int:
    """递归统计评论树中的全部节点数量。"""
    if not isinstance(replies, list):
        return 0

    total = 0
    stack: list[Any] = list(replies)
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        total += 1
        nested = node.get("replies")
        if isinstance(nested, list) and nested:
            stack.extend(nested)
    return total
