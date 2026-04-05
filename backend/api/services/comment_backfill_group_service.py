"""
评论补采任务组服务层。

负责将多个评论补采任务（comment_backfill）合并为一个大任务组，
加载所有源任务的待补采帖子，去重、排序，为任务组提供合并后的帖子列表。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GroupSourceTaskResult:
    """单个源任务在合并中的处理结果"""
    source_task_id: str
    source_keyword: str = ""
    platform: str = "x"
    task_status: str = ""
    post_count: int = 0          # 本次贡献的帖子数（去重前）
    status: str = "skipped"      # "included" | "skipped"
    reason: str = ""


@dataclass
class GroupMergeResult:
    """任务组合并结果"""
    tweets: list[dict] = field(default_factory=list)
    source_results: list[GroupSourceTaskResult] = field(default_factory=list)
    total_posts: int = 0          # 合并后去重帖子总数
    total_expected_replies: int = 0


def load_and_merge_group_posts(
    source_task_ids: list[str],
) -> GroupMergeResult:
    """
    从多个源任务（任意 task_kind）加载帖子，合并去重，返回用于补采的帖子列表。

    合并规则：
    - 只保留 metrics.replies > 0 的帖子
    - 已完整补采（replies 非空 且 comment_backfill_failed != True）的帖子跳过
    - 按 tweet_id 全局去重（相同帖子只保留一份）
    - 结果按 metrics.replies 降序排列，优先处理高价值帖子
    """
    import api.services.task_manager as task_manager

    merged: dict[str, dict] = {}          # tweet_id → tweet dict
    source_results: list[GroupSourceTaskResult] = []

    for task_id in source_task_ids:
        task = task_manager.get_task_full(task_id)
        if not task:
            source_results.append(GroupSourceTaskResult(
                source_task_id=task_id,
                status="skipped",
                reason="任务不存在",
            ))
            continue

        platform = str(task.get("platform") or "x").lower()
        if platform != "x":
            source_results.append(GroupSourceTaskResult(
                source_task_id=task_id,
                source_keyword=str(task.get("keyword") or ""),
                platform=platform,
                task_status=str(task.get("status") or ""),
                status="skipped",
                reason="任务组目前仅支持 X 平台",
            ))
            continue

        tweets = task_manager.get_task_tweets_ref(task_id)
        if not tweets:
            tweets = list(task.get("tweets") or [])

        if not tweets:
            source_results.append(GroupSourceTaskResult(
                source_task_id=task_id,
                source_keyword=str(task.get("keyword") or ""),
                platform=platform,
                task_status=str(task.get("status") or ""),
                status="skipped",
                reason="源任务没有帖子数据",
            ))
            continue

        contributed = 0
        for tweet in tweets:
            tweet_id = str(tweet.get("id") or "").strip()
            if not tweet_id:
                continue

            # 评论数为 0 的帖子没有补采价值
            reply_count = int((tweet.get("metrics") or {}).get("replies") or 0)
            if reply_count <= 0:
                continue

            # 已完整补采的帖子跳过（replies 非空且没有失败标记）
            if tweet.get("replies") is not None and not tweet.get("comment_backfill_failed"):
                continue

            # 全局去重：相同 tweet_id 只保留第一次出现的版本
            if tweet_id in merged:
                continue

            # 规范化：去掉旧的 replies / comment_stats 字段，确保干净入组
            clean_tweet = _normalize_tweet_for_group(tweet)
            merged[tweet_id] = clean_tweet
            contributed += 1

        source_results.append(GroupSourceTaskResult(
            source_task_id=task_id,
            source_keyword=str(task.get("keyword") or ""),
            platform=platform,
            task_status=str(task.get("status") or ""),
            post_count=contributed,
            status="included" if contributed > 0 else "skipped",
            reason="" if contributed > 0 else "该任务没有待补采的帖子（已全部处理或评论数均为 0）",
        ))

    if not merged:
        logger.warning("合并结果为空：所有源任务均无待补采帖子")
        return GroupMergeResult(source_results=source_results)

    # 按评论数降序排列，高价值帖子优先
    sorted_tweets = sorted(
        merged.values(),
        key=lambda t: int((t.get("metrics") or {}).get("replies") or 0),
        reverse=True,
    )

    total_expected_replies = sum(
        int((t.get("metrics") or {}).get("replies") or 0)
        for t in sorted_tweets
    )

    logger.info(
        "评论补采任务组合并完成: 源任务=%d, 合并后帖子=%d, 预期评论总数=%d",
        len(source_task_ids),
        len(sorted_tweets),
        total_expected_replies,
    )

    return GroupMergeResult(
        tweets=sorted_tweets,
        source_results=source_results,
        total_posts=len(sorted_tweets),
        total_expected_replies=total_expected_replies,
    )


def build_group_keyword(source_task_ids: list[str], group_name: Optional[str]) -> str:
    """根据源任务自动生成任务组名称"""
    if group_name and group_name.strip():
        return group_name.strip()

    import api.services.task_manager as task_manager

    keywords: list[str] = []
    for tid in source_task_ids[:3]:
        task = task_manager.get_task_summary(tid)
        if task:
            kw = str(task.get("keyword") or "").strip()
            # 去掉已有 "评论补采 · " 前缀
            for prefix in ("X 评论补采 · ", "微博 评论补采 · "):
                if kw.startswith(prefix):
                    kw = kw[len(prefix):]
                    break
            if kw:
                keywords.append(kw)

    if keywords:
        label = "、".join(keywords)
        if len(source_task_ids) > 3:
            label += f" 等 {len(source_task_ids)} 个任务"
        return f"X 评论补采任务组 · {label}"
    return f"X 评论补采任务组 · {len(source_task_ids)} 个任务"


def _normalize_tweet_for_group(tweet: dict) -> dict:
    """
    清理帖子字段，确保进入任务组时状态干净：
    - 移除旧的 replies / comment_backfill_failed / comment_stats（让补采任务重新采集）
    - 保留 id / author / content / metrics / url 等核心字段
    """
    clean = dict(tweet)
    clean.pop("replies", None)
    clean.pop("comment_backfill_failed", None)
    clean.pop("comment_stats", None)
    return clean
