"""
数据分析看板路由
GET /api/v1/analytics/overview     全局数据聚合统计
GET /api/v1/analytics/live-rates   运行中任务实时采集速率
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter

from api.services import task_manager

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _parse_date_only(iso_str: Optional[str]) -> Optional[str]:
    """从 ISO 时间字符串提取日期部分 YYYY-MM-DD。"""
    if not iso_str:
        return None
    try:
        return iso_str[:10]
    except Exception:
        return None


@router.get("/overview", summary="全局数据聚合统计")
async def get_overview():
    """遍历所有任务，聚合推文/评论/任务维度的统计数据。"""
    all_tasks = task_manager.list_tasks()

    # ── 汇总统计 ──
    total_tasks = len(all_tasks)
    total_tweets = 0
    total_replies = 0
    active_tasks = 0
    completed_tasks = 0
    recrawl_tasks = 0
    total_new_from_recrawl = 0

    # ── 每日采集量（按 created_at 分桶）──
    daily_map: dict[str, dict] = defaultdict(lambda: {
        "tweets": 0, "replies": 0, "tasks_created": 0,
    })

    # ── 平台分布 ──
    platform_map: dict[str, dict] = defaultdict(lambda: {
        "tasks": 0, "tweets": 0, "replies": 0,
    })

    # ── 关键词排行 ──
    keyword_map: dict[str, dict] = defaultdict(lambda: {
        "tasks": 0, "tweets": 0, "replies": 0,
    })

    for task in all_tasks:
        status = task.get("status", "")
        result_count = int(task.get("result_count", 0))
        replies_fetched = int(task.get("replies_fetched", 0))
        platform = task.get("platform", "x")
        keyword = task.get("keyword", "未知")
        source_task_id = task.get("source_task_id")
        exclude_count = int(task.get("exclude_count", 0))

        total_tweets += result_count
        total_replies += replies_fetched

        if status in ("pending", "running"):
            active_tasks += 1
        elif status == "done":
            completed_tasks += 1

        # 复爬任务统计
        if source_task_id and exclude_count > 0:
            recrawl_tasks += 1
            total_new_from_recrawl += result_count

        # 按天分桶
        created_date = _parse_date_only(task.get("created_at"))
        if created_date:
            bucket = daily_map[created_date]
            bucket["tweets"] += result_count
            bucket["replies"] += replies_fetched
            bucket["tasks_created"] += 1

        # 平台分布
        pm = platform_map[platform]
        pm["tasks"] += 1
        pm["tweets"] += result_count
        pm["replies"] += replies_fetched

        # 关键词（去掉 since/until 操作符，取前 40 字符避免过长）
        clean_kw = _clean_keyword(keyword)
        km = keyword_map[clean_kw]
        km["tasks"] += 1
        km["tweets"] += result_count
        km["replies"] += replies_fetched

    # 构建每日列表（按日期升序）
    daily_volume = sorted(
        [{"date": k, **v} for k, v in daily_map.items()],
        key=lambda x: x["date"],
    )

    # 平台分布列表
    platform_distribution = [
        {"platform": k, **v} for k, v in sorted(platform_map.items())
    ]

    # 关键词排行（按推文数降序，取前 20）
    top_keywords = sorted(
        [{"keyword": k, **v} for k, v in keyword_map.items()],
        key=lambda x: x["tweets"],
        reverse=True,
    )[:20]

    return {
        "summary": {
            "total_tasks": total_tasks,
            "total_tweets": total_tweets,
            "total_replies": total_replies,
            "active_tasks": active_tasks,
            "completed_tasks": completed_tasks,
            "recrawl_tasks": recrawl_tasks,
            "total_new_from_recrawl": total_new_from_recrawl,
        },
        "daily_volume": daily_volume,
        "platform_distribution": platform_distribution,
        "top_keywords": top_keywords,
    }


@router.get("/live-rates", summary="运行中任务实时采集速率")
async def get_live_rates():
    """汇总所有 running 状态任务的 telemetry 实时速率数据。

    返回全局聚合速率 + 每任务速率明细，前端可用于实时看板。
    """
    from crawler import telemetry

    all_tasks = task_manager.list_tasks()

    running_tasks = [
        t for t in all_tasks
        if t.get("status") in ("running",)
    ]

    # ── 全局聚合 ──
    global_tweets_15s = 0.0
    global_tweets_60s = 0.0
    global_replies_15s = 0.0
    global_replies_60s = 0.0
    global_total_tweets = 0
    global_total_replies = 0

    # ── 每任务明细 ──
    task_rates: list[dict] = []

    for task in running_tasks:
        task_id = task.get("task_id", "")
        live = task.get("live_metrics", {})

        t15 = float(live.get("tweets_per_min_15s", 0))
        t60 = float(live.get("tweets_per_min_60s", 0))
        r15 = float(live.get("replies_per_min_15s", 0))
        r60 = float(live.get("replies_per_min_60s", 0))
        elapsed = int(live.get("elapsed_sec", 0))
        idle = int(live.get("idle_sec", 0))

        result_count = int(task.get("result_count", 0))
        replies_fetched = int(task.get("replies_fetched", 0))

        global_tweets_15s += t15
        global_tweets_60s += t60
        global_replies_15s += r15
        global_replies_60s += r60
        global_total_tweets += result_count
        global_total_replies += replies_fetched

        # 推算每小时速率（基于 60s 窗口的速率 × 60）
        tweets_per_hour = round(t60 * 60, 1)
        replies_per_hour = round(r60 * 60, 1)

        task_rates.append({
            "task_id": task_id,
            "keyword": task.get("keyword", ""),
            "platform": task.get("platform", "x"),
            "crawl_phase": task.get("crawl_phase", ""),
            "result_count": result_count,
            "replies_fetched": replies_fetched,
            "tweets_per_min_15s": round(t15, 2),
            "tweets_per_min_60s": round(t60, 2),
            "replies_per_min_15s": round(r15, 2),
            "replies_per_min_60s": round(r60, 2),
            "tweets_per_hour": tweets_per_hour,
            "replies_per_hour": replies_per_hour,
            "elapsed_sec": elapsed,
            "idle_sec": idle,
        })

    # 全局每小时速率
    global_tweets_per_hour = round(global_tweets_60s * 60, 1)
    global_replies_per_hour = round(global_replies_60s * 60, 1)

    return {
        "running_count": len(running_tasks),
        "global_rates": {
            "tweets_per_min_15s": round(global_tweets_15s, 2),
            "tweets_per_min_60s": round(global_tweets_60s, 2),
            "replies_per_min_15s": round(global_replies_15s, 2),
            "replies_per_min_60s": round(global_replies_60s, 2),
            "tweets_per_hour": global_tweets_per_hour,
            "replies_per_hour": global_replies_per_hour,
            "total_tweets": global_total_tweets,
            "total_replies": global_total_replies,
        },
        "task_rates": task_rates,
    }


# ── 工具函数 ──────────────────────────────────────────────────────

_OPERATOR_RE = re.compile(
    r"\b(?:since|until|from|to|lang|min_faves|min_retweets|min_replies):\S+",
    re.IGNORECASE,
)


def _clean_keyword(keyword: str) -> str:
    """去掉搜索操作符，保留核心关键词，截断到 40 字符。"""
    cleaned = _OPERATOR_RE.sub("", keyword).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return keyword[:40]
    return cleaned[:40]
