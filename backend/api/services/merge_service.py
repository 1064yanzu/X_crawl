"""
任务合并服务

职责：
- find_mergeable_groups()  : 按“关键词核心 token 有交集”+ platform + task_kind 分组
- preview_merge()          : 返回合并预览——每组的统计信息和去重预估
- execute_merge()          : 执行合并——加载 tweets、去重、保存到 target、删除源任务

设计原则：
- 仅合并非活跃任务（done / stopped / failed），running / pending / paused 不参与
- 关键词少的任务可并入关键词更多、更具体的任务
- target 优先选择“关键词更完整”的任务；同等情况下再按创建时间更早优先
- 推文按 tweet.id 去重，优先保留 replies 数据更完整的版本
"""
from __future__ import annotations

import copy
import logging
import re
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

# 允许合并的终态状态
_MERGEABLE_STATUSES = {"done", "stopped", "failed"}


def _get_task_manager():
    from api.services import task_manager
    return task_manager


def _get_task_db():
    from api.services import task_db
    return task_db


def _parse_iso_for_sort(iso_str: str | None) -> str:
    """将 ISO 字符串转为可排序字符串，None 排到最后。"""
    return iso_str or "9999-12-31T23:59:59"


_QUERY_OPERATORS = {
    "or",
    "and",
    "since",
    "until",
    "lang",
    "min_faves",
    "min_replies",
    "min_retweets",
    "filter",
    "-filter",
}


def _normalize_keyword(kw: str) -> str:
    return re.sub(r"\s+", " ", kw.strip()).casefold()


def _extract_keyword_tokens(kw: str) -> set[str]:
    normalized = _normalize_keyword(kw)
    raw_tokens = re.split(r"\s+", normalized)
    tokens: set[str] = set()

    for token in raw_tokens:
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            key = token.split(":", 1)[0]
            if key in _QUERY_OPERATORS:
                continue
        token = token.strip("()[]{}\"'.,!?，。！？；;")
        if not token or token in _QUERY_OPERATORS:
            continue
        if re.fullmatch(r"[\d:-]+", token):
            continue
        if len(token) <= 1 and token.isascii():
            continue
        tokens.add(token)

    return tokens


def _keywords_related(left: str, right: str) -> bool:
    left_tokens = _extract_keyword_tokens(left)
    right_tokens = _extract_keyword_tokens(right)
    if left_tokens and right_tokens:
        return bool(left_tokens & right_tokens)
    return _normalize_keyword(left) == _normalize_keyword(right)


def _pick_target_task(tasks: list[dict]) -> dict:
    return sorted(
        tasks,
        key=lambda task: (
            -len(_extract_keyword_tokens(task.get("keyword", ""))),
            -len(_normalize_keyword(task.get("keyword", ""))),
            _parse_iso_for_sort(task.get("created_at")),
        ),
    )[0]

def find_mergeable_groups(
    task_ids: list[str],
) -> tuple[list[dict], list[str]]:
    """
    将指定 task_ids 按 keyword + platform 分组。

    Returns:
        (groups, non_mergeable_ids)
        - groups: 每组包含 { key, keyword, platform, task_ids, tasks }
        - non_mergeable_ids: 不满足合并条件的 task_id 列表
    """
    tm = _get_task_manager()
    non_mergeable: list[str] = []
    # 先按 platform + task_kind 粗分，再按关键词交集做连通分组
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for tid in task_ids:
        task = tm.get_task_summary(tid)
        if not task:
            non_mergeable.append(tid)
            continue
        if task.get("status") not in _MERGEABLE_STATUSES:
            non_mergeable.append(tid)
            continue
            
        platform = task.get("platform", "x")
        task_kind = task.get("task_kind", "search")
        key = (platform, task_kind)
        buckets[key].append(task)

    groups: list[dict] = []
    for (platform, _task_kind), tasks in buckets.items():
        if len(tasks) < 2:
            non_mergeable.extend(t["task_id"] for t in tasks)
            continue

        remaining = sorted(tasks, key=lambda t: _parse_iso_for_sort(t.get("created_at")))
        raw_groups: list[list[dict]] = []

        while remaining:
            seed = remaining.pop(0)
            component = [seed]
            changed = True
            while changed:
                changed = False
                next_remaining: list[dict] = []
                for candidate in remaining:
                    if any(_keywords_related(candidate["keyword"], existed["keyword"]) for existed in component):
                        component.append(candidate)
                        changed = True
                    else:
                        next_remaining.append(candidate)
                remaining = next_remaining
            raw_groups.append(component)

        for component in raw_groups:
            if len(component) < 2:
                non_mergeable.extend(t["task_id"] for t in component)
                continue

            target = _pick_target_task(component)
            tasks_sorted = sorted(
                component,
                key=lambda task: (
                    0 if task["task_id"] == target["task_id"] else 1,
                    _parse_iso_for_sort(task.get("created_at")),
                ),
            )

            keyword_tags = list(dict.fromkeys(t["keyword"] for t in tasks_sorted))
            display_keyword = target["keyword"] if len(keyword_tags) == 1 else target["keyword"] + f" (及另外 {len(keyword_tags)-1} 个相关关键词)"

            groups.append({
                "keyword": display_keyword,
                "target_keyword": target["keyword"],
                "platform": platform,
                "task_count": len(tasks_sorted),
                "target_task_id": target["task_id"],
                "source_task_ids": [t["task_id"] for t in tasks_sorted if t["task_id"] != target["task_id"]],
                "tasks": tasks_sorted,
            })

    return groups, non_mergeable


def preview_merge(task_ids: list[str]) -> dict:
    """
    返回合并预览信息。

    Returns:
        {
            "groups": [
                {
                    "keyword": "...",
                    "platform": "x",
                    "task_count": 3,
                    "target_task_id": "...",
                    "source_task_ids": ["...", "..."],
                    "tasks_summary": [
                        { "task_id": "...", "result_count": 120, "status": "done", "created_at": "...", "is_target": True },
                        ...
                    ],
                    "total_tweets": 350,
                    "estimated_unique_tweets": 280,
                }
            ],
            "mergeable_group_count": 2,
            "total_mergeable_tasks": 6,
            "non_mergeable_task_ids": ["..."],
        }
    """
    groups, non_mergeable = find_mergeable_groups(task_ids)
    db = _get_task_db()

    result_groups: list[dict] = []
    total_mergeable = 0

    for group in groups:
        total_tweets = 0
        all_tweet_ids: set[str] = set()
        tasks_summary: list[dict] = []

        for task in group["tasks"]:
            tid = task["task_id"]
            result_count = task.get("result_count", 0)
            total_tweets += result_count

            # 快速加载 tweet_ids 用于去重估算
            tweets = db.load_task_result(tid)
            for tw in tweets:
                tw_id = tw.get("id")
                if tw_id:
                    all_tweet_ids.add(str(tw_id))

            tasks_summary.append({
                "task_id": tid,
                "result_count": result_count,
                "status": task.get("status"),
                "created_at": task.get("created_at"),
                "finished_at": task.get("finished_at"),
                "is_target": tid == group["target_task_id"],
            })

        total_mergeable += group["task_count"]
        result_groups.append({
            "keyword": group["keyword"],
            "platform": group["platform"],
            "task_count": group["task_count"],
            "target_task_id": group["target_task_id"],
            "source_task_ids": group["source_task_ids"],
            "tasks_summary": tasks_summary,
            "total_tweets": total_tweets,
            "estimated_unique_tweets": len(all_tweet_ids),
        })

    return {
        "groups": result_groups,
        "mergeable_group_count": len(result_groups),
        "total_mergeable_tasks": total_mergeable,
        "non_mergeable_task_ids": non_mergeable,
    }


def _deduplicate_tweets(all_tweets: list[dict]) -> list[dict]:
    """
    对推文列表按 ID 去重。

    当同 ID 推文出现多次时，优先保留 replies 字段更丰富（数量更多）的版本。
    """
    seen: dict[str, dict] = {}

    for tw in all_tweets:
        tw_id = str(tw.get("id", ""))
        if not tw_id:
            continue

        if tw_id not in seen:
            seen[tw_id] = tw
            continue

        # 保留 replies 更多的版本
        existing_replies = seen[tw_id].get("replies") or []
        new_replies = tw.get("replies") or []
        if len(new_replies) > len(existing_replies):
            seen[tw_id] = tw

    return list(seen.values())


def _merge_time_coverage(coverages: list[dict]) -> dict:
    """合并多个 time_coverage 字典。"""
    from api.services.task_manager import _merge_coverage

    merged: dict = {}
    for cov in coverages:
        merged = _merge_coverage(merged, cov)
    return merged


def execute_merge(task_ids: list[str]) -> dict:
    """
    执行合并操作。

    Returns:
        {
            "merged_groups": [
                {
                    "keyword": "...",
                    "platform": "x",
                    "target_task_id": "...",
                    "deleted_task_ids": ["...", "..."],
                    "original_total_tweets": 350,
                    "merged_unique_tweets": 280,
                }
            ],
            "total_deleted_tasks": 4,
            "total_unique_tweets": 560,
        }
    """
    groups, non_mergeable = find_mergeable_groups(task_ids)

    if not groups:
        return {
            "merged_groups": [],
            "total_deleted_tasks": 0,
            "total_unique_tweets": 0,
            "non_mergeable_task_ids": non_mergeable,
        }

    tm = _get_task_manager()
    db = _get_task_db()

    merged_groups: list[dict] = []
    total_deleted = 0
    total_unique = 0

    for group in groups:
        keyword = group["keyword"]
        target_keyword = group.get("target_keyword") or keyword
        platform = group["platform"]
        target_id = group["target_task_id"]
        source_ids = group["source_task_ids"]

        logger.info(
            "开始合并: keyword=%s, platform=%s, target=%s, sources=%s",
            keyword, platform, target_id[:8], [s[:8] for s in source_ids],
        )

        # 1. 加载所有任务的 tweets
        all_tweets: list[dict] = []
        original_total = 0
        coverages: list[dict] = []
        total_replies = 0

        all_task_ids = [target_id] + source_ids
        for tid in all_task_ids:
            tweets = db.load_task_result(tid)
            all_tweets.extend(tweets)
            original_total += len(tweets)

            task_snapshot = tm.get_task_summary(tid)
            if task_snapshot:
                coverages.append(task_snapshot.get("time_coverage", {}))
                total_replies += task_snapshot.get("replies_fetched", 0)

        # 2. 去重
        unique_tweets = _deduplicate_tweets(all_tweets)

        # 3. 合并 time_coverage
        merged_coverage = _merge_time_coverage(coverages)

        # 4. 重新统计 replies
        from api.services.task_insights import summarize_tweets
        computed_replies, computed_coverage = summarize_tweets(unique_tweets)
        # 使用计算出来的覆盖范围（更准确）
        final_coverage = computed_coverage if computed_coverage else merged_coverage

        # 5. 更新 target 任务
        from api.services.task_manager import (
            _tasks, _tasks_lock, _set_task_result_locked, _make_preview,
            _persist_force, _touch,
        )
        with _tasks_lock:
            target = _tasks.get(target_id)
            if target:
                _set_task_result_locked(target_id, unique_tweets)
                target.update({
                    "keyword": target_keyword,
                    "result_count": len(unique_tweets),
                    "preview_tweets": _make_preview(unique_tweets),
                    "replies_fetched": max(total_replies, computed_replies),
                    "time_coverage": final_coverage,
                    "quality_state": "complete",
                })
                _touch(target)

        # 强制持久化 target
        _persist_force(target_id, full=True)

        # 6. 删除源任务
        deleted_ids: list[str] = []
        for sid in source_ids:
            success = tm.delete_task(sid)
            if success:
                deleted_ids.append(sid)
                logger.info("合并: 已删除源任务 %s", sid[:8])
            else:
                logger.warning("合并: 删除源任务失败 %s", sid[:8])

        total_deleted += len(deleted_ids)
        total_unique += len(unique_tweets)

        merged_groups.append({
            "keyword": keyword,
            "platform": platform,
            "target_task_id": target_id,
            "deleted_task_ids": deleted_ids,
            "original_total_tweets": original_total,
            "merged_unique_tweets": len(unique_tweets),
        })

        logger.info(
            "合并完成: keyword=%s, 原始=%d → 去重后=%d, 删除了=%d个源任务",
            keyword, original_total, len(unique_tweets), len(deleted_ids),
        )

    return {
        "merged_groups": merged_groups,
        "total_deleted_tasks": total_deleted,
        "total_unique_tweets": total_unique,
        "non_mergeable_task_ids": non_mergeable,
    }
