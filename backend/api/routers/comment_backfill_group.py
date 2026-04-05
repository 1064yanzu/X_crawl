"""
评论补采任务组路由。

提供将多个评论补采任务（comment_backfill）合并为一个大任务组的接口。
任务组在执行时使用完全解耦的 L1/L2 浏览器，实现最高的爬取效率。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.task import (
    CommentBackfillGroupRequest,
    CommentBackfillGroupResponse,
    CommentBackfillGroupSourceSummary,
    TaskOut,
)
from api.services import crawl_service, task_manager
from api.services.comment_backfill_group_service import (
    GroupSourceTaskResult,
    build_group_keyword,
    load_and_merge_group_posts,
)

router = APIRouter(
    prefix="/api/v1/comment-backfill",
    tags=["评论补采"],
)


@router.post(
    "/group",
    response_model=CommentBackfillGroupResponse,
    summary="将多个评论补采任务合并为一个任务组",
    description=(
        "从多个已有任务（任意 task_kind）中加载待补采帖子，合并去重，"
        "创建一个 `comment_backfill_group` 类型的大任务并立即启动。\n\n"
        "任务组执行时使用三个独立的 Chrome 进程：\n"
        "- 主浏览器：任务生命周期管理\n"
        "- L1浏览器×N：并行抓取一级评论（reply_worker_count≥2）\n"
        "- L2浏览器：专用于二级评论（完全独立，消除 CDP 竞争）\n\n"
        "源任务的已完成帖子自动跳过，只补采未处理或之前失败的帖子。"
    ),
)
async def create_comment_backfill_group(
    req: CommentBackfillGroupRequest,
) -> CommentBackfillGroupResponse:
    # 去重并规范化源 task_id 列表
    seen: set[str] = set()
    source_task_ids: list[str] = []
    for tid in req.source_task_ids:
        tid = tid.strip()
        if tid and tid not in seen:
            seen.add(tid)
            source_task_ids.append(tid)

    if not source_task_ids:
        raise HTTPException(status_code=400, detail="source_task_ids 不能为空")

    # 合并各源任务的待补采帖子
    merge_result = load_and_merge_group_posts(source_task_ids)

    if not merge_result.tweets:
        included = [r for r in merge_result.source_results if r.status == "included"]
        raise HTTPException(
            status_code=400,
            detail=(
                "合并后没有待补采的帖子。"
                "请确认所选任务中存在未补采的 X 帖子（评论数 > 0 且未完成补采）。"
            ),
        )

    keyword = build_group_keyword(source_task_ids, req.group_name)
    total_expected_replies = merge_result.total_expected_replies

    # 创建任务组任务
    group_task_id = task_manager.create_task(
        keyword=keyword,
        product="Comments",
        fetch_replies=True,
        max_replies_per_tweet=req.max_replies_per_tweet,
        reply_depth=req.reply_depth,
        crawl_strategy="bfs",
        platform="x",
        task_kind="comment_backfill_group",
        source_task_id=None,
        source_task_ids=source_task_ids,
        concurrency=req.concurrency,
        comment_backfill_progress={
            "total_posts": merge_result.total_posts,
            "eligible_posts": merge_result.total_posts,
            "processed_posts": 0,
            "skipped_posts": 0,
            "succeeded_posts": 0,
            "failed_posts": 0,
            "total_expected_replies": total_expected_replies,
        },
    )

    # 写入合并后的种子帖子
    task_manager.set_task_seed_tweets(group_task_id, merge_result.tweets, current_page=0)

    task = task_manager.get_task_summary(group_task_id)
    if not task:
        raise HTTPException(status_code=500, detail="评论补采任务组创建失败")

    # 启动任务
    crawl_service.start_crawler_thread(
        task_id=group_task_id,
        task=task,
        resume=True,
    )
    refreshed = task_manager.get_task_summary(group_task_id) or task

    sources = [
        _to_source_summary(r) for r in merge_result.source_results
    ]

    return CommentBackfillGroupResponse(
        group_task_id=group_task_id,
        group_task=TaskOut(**refreshed),
        total_posts=merge_result.total_posts,
        source_count=len([r for r in merge_result.source_results if r.status == "included"]),
        sources=sources,
    )


def _to_source_summary(r: GroupSourceTaskResult) -> CommentBackfillGroupSourceSummary:
    return CommentBackfillGroupSourceSummary(
        source_task_id=r.source_task_id,
        source_keyword=r.source_keyword,
        platform=r.platform,
        task_status=r.task_status,
        post_count=r.post_count,
        status=r.status,
        reason=r.reason,
    )
