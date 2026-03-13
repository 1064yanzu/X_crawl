"""微博关键词规划。

默认保留用户输入的完整关键词；仅在显式开启时，才把简单顶层 OR 表达式拆成多个子查询。
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class WeiboQueryPlan:
    raw_keyword: str
    normalized_keyword: str
    variants: tuple[str, ...]
    uses_or_split: bool = False


def build_weibo_query_plan(keyword: str, *, enable_or_split: bool = True) -> WeiboQueryPlan:
    normalized = re.sub(r"\s+", " ", (keyword or "").strip())
    if not normalized:
        return WeiboQueryPlan(
            raw_keyword=keyword,
            normalized_keyword="",
            variants=tuple(),
            uses_or_split=False,
        )

    if not enable_or_split:
        return WeiboQueryPlan(
            raw_keyword=keyword,
            normalized_keyword=normalized,
            variants=(normalized,),
            uses_or_split=False,
        )

    stripped = _strip_wrapping_parentheses(normalized)
    variants = tuple(
        cleaned
        for part in _split_top_level_or(stripped)
        if (cleaned := _strip_wrapping_parentheses(part).strip())
    )
    if len(variants) <= 1:
        return WeiboQueryPlan(
            raw_keyword=keyword,
            normalized_keyword=normalized,
            variants=(normalized,),
            uses_or_split=False,
        )

    return WeiboQueryPlan(
        raw_keyword=keyword,
        normalized_keyword=normalized,
        variants=variants,
        uses_or_split=True,
    )


def _split_top_level_or(expression: str) -> list[str]:
    text = expression.strip()
    if not text:
        return []

    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
            i += 1
            continue

        if ch in {'"', "'"}:
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0 and text[i : i + 4].upper() == " OR ":
            parts.append(text[start:i].strip())
            start = i + 4
            i = start
            continue
        i += 1

    parts.append(text[start:].strip())
    return parts


def _strip_wrapping_parentheses(text: str) -> str:
    value = text.strip()
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        balanced = True
        for index, ch in enumerate(value):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    balanced = False
                    break
                if depth == 0 and index != len(value) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            break
        value = value[1:-1].strip()
    return value
