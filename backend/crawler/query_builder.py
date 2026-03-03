"""
X 搜索操作符构建工具

将结构化的高级搜索参数转换为 X (Twitter) 搜索操作符字符串。
与前端 buildAdvancedQuery() 保持逻辑一致。

用法示例:
    from crawler.query_builder import build_advanced_query

    query = build_advanced_query(
        all_words="AI 人工智能",
        exact_phrase="machine learning",
        from_accounts="elonmusk",
        min_faves=1000,
        since="2024-01-01",
    )
    # => 'AI 人工智能 "machine learning" from:elonmusk min_faves:1000 since:2024-01-01'
"""
from typing import Optional, Literal


ReplyFilter = Literal["off", "include", "only"]
LinkFilter = Literal["off", "include", "only"]


def build_advanced_query(
    *,
    all_words: str = "",
    exact_phrase: str = "",
    any_words: str = "",
    none_words: str = "",
    hashtags: str = "",
    lang: str = "",
    from_accounts: str = "",
    to_accounts: str = "",
    mention_accounts: str = "",
    reply_filter: ReplyFilter = "off",
    link_filter: LinkFilter = "off",
    min_replies: Optional[int] = None,
    min_faves: Optional[int] = None,
    min_retweets: Optional[int] = None,
    since: str = "",
    until: str = "",
) -> str:
    """
    将高级搜索参数构建为 X 搜索操作符字符串。

    Args:
        all_words:        包含全部这些词（空格分隔）
        exact_phrase:     包含精确短语
        any_words:        包含任意这些词（空格分隔，将用 OR 连接）
        none_words:       排除这些词（空格分隔，各自加 - 前缀）
        hashtags:         包含这些 Hashtag（空格分隔）
        lang:             语言代码（如 en, zh, ja）
        from_accounts:    来自这些账号（空格或逗号分隔）
        to_accounts:      发给这些账号（空格或逗号分隔）
        mention_accounts: 提及这些账号（空格或逗号分隔）
        reply_filter:     回复筛选: off / include / only
        link_filter:      链接筛选: off / include / only
        min_replies:      最低回复数
        min_faves:        最低点赞数
        min_retweets:     最低转发数
        since:            起始日期（YYYY-MM-DD）
        until:            结束日期（YYYY-MM-DD）

    Returns:
        拼接好的搜索操作符字符串
    """
    parts: list[str] = []

    # All of these words
    if all_words and all_words.strip():
        parts.append(all_words.strip())

    # Exact phrase → "phrase"
    if exact_phrase and exact_phrase.strip():
        parts.append(f'"{exact_phrase.strip()}"')

    # Any of these words → word1 OR word2
    if any_words and any_words.strip():
        words = any_words.strip().split()
        if len(words) > 1:
            parts.append(f"({' OR '.join(words)})")
        elif words:
            parts.append(words[0])

    # None of these words → -word1 -word2
    if none_words and none_words.strip():
        for w in none_words.strip().split():
            parts.append(f"-{w}")

    # Hashtags → #tag1 #tag2
    if hashtags and hashtags.strip():
        for tag in hashtags.strip().split():
            parts.append(tag if tag.startswith("#") else f"#{tag}")

    # Language
    if lang and lang.strip():
        parts.append(f"lang:{lang.strip()}")

    # From accounts → from:user1 OR from:user2
    if from_accounts and from_accounts.strip():
        accounts = [a.lstrip("@") for a in _split_accounts(from_accounts)]
        if len(accounts) > 1:
            parts.append(f"({' OR '.join(f'from:{a}' for a in accounts)})")
        elif accounts:
            parts.append(f"from:{accounts[0]}")

    # To accounts → to:user1 OR to:user2
    if to_accounts and to_accounts.strip():
        accounts = [a.lstrip("@") for a in _split_accounts(to_accounts)]
        if len(accounts) > 1:
            parts.append(f"({' OR '.join(f'to:{a}' for a in accounts)})")
        elif accounts:
            parts.append(f"to:{accounts[0]}")

    # Mentioning accounts → @user1 @user2
    if mention_accounts and mention_accounts.strip():
        for a in _split_accounts(mention_accounts):
            parts.append(a if a.startswith("@") else f"@{a}")

    # Reply filter
    if reply_filter == "only":
        parts.append("filter:replies")

    # Link filter
    if link_filter == "only":
        parts.append("filter:links")

    # Engagement
    if min_replies is not None and min_replies > 0:
        parts.append(f"min_replies:{min_replies}")
    if min_faves is not None and min_faves > 0:
        parts.append(f"min_faves:{min_faves}")
    if min_retweets is not None and min_retweets > 0:
        parts.append(f"min_retweets:{min_retweets}")

    # Dates
    if since and since.strip():
        parts.append(f"since:{since.strip()}")
    if until and until.strip():
        parts.append(f"until:{until.strip()}")

    return " ".join(parts)


def _split_accounts(s: str) -> list[str]:
    """按空格或逗号分隔账号，去除空元素。"""
    import re
    return [a for a in re.split(r"[\s,]+", s.strip()) if a]
