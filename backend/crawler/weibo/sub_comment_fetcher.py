"""
微博子评论（楼中楼）抓取器。

使用 buildComments API 的 fetch_level=1 参数获取每条顶层评论下的全部子评论。

精准过滤策略（基于数据分析验证）：
  - 评论级别的 total_number 是可靠的（319 条中 0 条不一致）
  - 仅对 total_number > len(comments) 的评论发起子评论请求
  - 同时检查 more_info.text 中的"共X条回复"作为兜底
  - 典型场景：320 条顶层中仅 ~5 条需要额外请求，避免触发风控

API 参数：
  - id = 顶层评论 ID（不是帖子 MID）
  - fetch_level = 1（子评论模式，0 为帖子顶层评论）
  - is_mix = 0
  - count = 20
  - max_id = 分页游标
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Callable, Optional

import requests as http_requests

logger = logging.getLogger(__name__)

# 子评论 API 基础 URL
SUB_COMMENT_API_BASE = "https://weibo.com/ajax/statuses/buildComments"

# 每页最大条数
_COUNT_PER_PAGE = 20

# 最大翻页数（单条评论的子评论分页上限）
_MAX_PAGES = 20

# 连续空页容忍次数
_MAX_EMPTY = 2

# 从 more_info.text 中提取回复数的正则
_MORE_INFO_RE = re.compile(r"共(\d+)条回复")


def _build_sub_comment_url(
    comment_id: int | str, max_id: int = 0
) -> str:
    """构建子评论 API URL。"""
    params = [
        "flow=0",
        "is_reload=1",
        f"id={comment_id}",
        "is_show_bulletin=2",
        "is_mix=0",
    ]
    if max_id:
        params.append(f"max_id={max_id}")
    params.extend([
        f"count={_COUNT_PER_PAGE}",
        "fetch_level=1",
        "locale=zh-CN",
    ])
    return f"{SUB_COMMENT_API_BASE}?{'&'.join(params)}"


def _get_real_sub_count(comment: dict) -> int:
    """
    获取评论的真实子评论数量（取 total_number 和 more_info 中的较大值）。

    API 返回的 total_number 通常可靠，但 more_info.text 中"共X条回复"
    可能包含更准确的数值。取两者的最大值作为兜底。
    """
    claimed = comment.get("total_number", 0)

    more_info = comment.get("more_info")
    if isinstance(more_info, dict):
        text = more_info.get("text", "")
        m = _MORE_INFO_RE.search(text)
        if m:
            more_count = int(m.group(1))
            claimed = max(claimed, more_count)

    return claimed


def fetch_sub_comments(
    comment_id: int | str,
    session: http_requests.Session,
    headers: dict[str, str],
    *,
    page_interval: float = 2.0,
    task_id: str | None = None,
) -> list[dict]:
    """
    获取某条顶层评论的全部子评论。

    Args:
        comment_id:     顶层评论 ID
        session:        已注入 Cookie 的 requests.Session
        headers:        完整的 API 请求头
        page_interval:  分页间隔（秒）
        task_id:        任务 ID

    Returns:
        子评论原始 dict 列表，或空列表
    """
    from crawler.utils import check_signal

    all_subs: list[dict] = []
    seen_ids: set[str] = set()
    max_id = 0
    empty_count = 0

    for page in range(1, _MAX_PAGES + 1):
        if task_id:
            try:
                check_signal(task_id)
            except Exception:
                break

        url = _build_sub_comment_url(comment_id, max_id=max_id)

        try:
            resp = session.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.debug(
                    f"子评论 API HTTP {resp.status_code}，"
                    f"comment_id={comment_id}"
                )
                break

            data = resp.json()
        except Exception as e:
            logger.debug(f"子评论 API 请求异常: {e}")
            break

        if data.get("ok") != 1:
            break

        page_data = data.get("data", [])
        max_id = data.get("max_id", 0)

        # 去重
        new_count = 0
        for sc in page_data:
            sc_id = str(sc.get("id", ""))
            if sc_id and sc_id in seen_ids:
                continue
            if sc_id:
                seen_ids.add(sc_id)
            all_subs.append(sc)
            new_count += 1

        if new_count == 0:
            empty_count += 1
            if empty_count >= _MAX_EMPTY:
                break
        else:
            empty_count = 0

        # 无更多分页
        if not max_id:
            break

        # 翻页间隔
        if page < _MAX_PAGES:
            time.sleep(page_interval)

    return all_subs


def enrich_comments_with_subs(
    comments_raw: list[dict],
    session: http_requests.Session,
    headers: dict[str, str],
    *,
    page_interval: float = 2.0,
    task_id: str | None = None,
    phase_callback: Callable[[str], None] | None = None,
) -> int:
    """
    对一批顶层评论，智能判断并补全子评论。

    使用 total_number + more_info 双重判断哪些评论有未获取的子评论，
    仅对需要补全的评论发起 API 请求（通常仅占总数的 1~5%）。

    Args:
        comments_raw:    顶层评论原始 dict 列表（会被修改）
        session:         已注入 Cookie 的 requests.Session
        headers:         完整的 API 请求头
        page_interval:   请求间隔（秒）
        task_id:         任务 ID
        phase_callback:  进度回调函数

    Returns:
        新增获取的子评论总数
    """
    total_new = 0
    total_comments = len(comments_raw)

    # 先统计需要补全的评论
    need_fetch: list[tuple[int, dict, int]] = []  # (index, comment, claimed)
    for i, c in enumerate(comments_raw):
        claimed = _get_real_sub_count(c)
        inline = len(c.get("comments", []))
        if claimed > inline:
            need_fetch.append((i, c, claimed))

    if not need_fetch:
        logger.info(f"子评论补全：{total_comments} 条顶层评论均无需补全")
        if phase_callback:
            phase_callback(f"所有 {total_comments} 条顶层评论子评论已完整")
        return 0

    logger.info(
        f"子评论补全：{len(need_fetch)}/{total_comments} 条评论需要补全子评论"
    )
    if phase_callback:
        phase_callback(
            f"开始抓取二级评论（{len(need_fetch)}/{total_comments} 条需要补全）"
        )

    for seq, (idx, c, claimed) in enumerate(need_fetch):
        comment_id = c.get("id", "")
        if not comment_id:
            continue

        inline = len(c.get("comments", []))

        logger.debug(
            f"子评论补全 [{seq+1}/{len(need_fetch)}] id={comment_id}，"
            f"声称 {claimed} 条，已有 {inline} 条"
        )

        subs = fetch_sub_comments(
            comment_id,
            session=session,
            headers=headers,
            page_interval=page_interval,
            task_id=task_id,
        )

        if subs:
            c["comments"] = subs
            new_got = len(subs) - inline
            if new_got > 0:
                total_new += new_got

        # 进度推送
        if phase_callback:
            phase_callback(
                f"二级评论 {seq+1}/{len(need_fetch)}，"
                f"已获取 {total_new} 条新子评论"
            )

        # 请求间间隔
        if seq < len(need_fetch) - 1:
            time.sleep(page_interval * 0.5)

    logger.info(
        f"子评论补全完成：{len(need_fetch)} 条评论，新增 {total_new} 条子评论"
    )

    return total_new
