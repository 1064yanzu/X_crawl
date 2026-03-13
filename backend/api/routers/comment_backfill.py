from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile

from api.schemas.comment_backfill import (
    CommentBackfillAnalyzeResponse,
    CommentBackfillImportResponse,
)
from api.schemas.task import TaskOut
from api.services import crawl_service, task_manager
from api.services.comment_backfill_importer import analyze_comment_backfill_file

router = APIRouter(prefix="/api/v1/comment-backfill", tags=["评论补采"])


@router.post(
    "/analyze",
    response_model=CommentBackfillAnalyzeResponse,
    summary="分析评论补采导入文件",
)
async def analyze_comment_backfill(
    file: UploadFile = File(...),
    platform: Literal["x", "weibo"] = Form(...),
) -> CommentBackfillAnalyzeResponse:
    content = await file.read()
    result = analyze_comment_backfill_file(file.filename or "import.csv", content, platform=platform)  # type: ignore[arg-type]
    return CommentBackfillAnalyzeResponse(**result.summary)


@router.post(
    "/import",
    response_model=CommentBackfillImportResponse,
    summary="导入导出文件并创建评论补采任务",
)
async def import_comment_backfill(
    file: UploadFile = File(...),
    platform: Literal["x", "weibo"] = Form(...),
    reply_depth: int = Form(2),
    max_replies_per_tweet: int = Form(0),
) -> CommentBackfillImportResponse:
    content = await file.read()
    result = analyze_comment_backfill_file(file.filename or "import.csv", content, platform=platform)  # type: ignore[arg-type]

    source_file_name = file.filename or "import.csv"
    platform_label = "X" if platform == "x" else "微博"
    keyword = f"{platform_label} 评论补采 · {source_file_name}"
    progress = {
        "total_posts": result.summary["unique_post_count"],
        "eligible_posts": result.summary["eligible_posts"],
        "processed_posts": 0,
        "skipped_posts": max(
            0,
            result.summary["unique_post_count"] - result.summary["eligible_posts"],
        ),
        "succeeded_posts": 0,
        "failed_posts": 0,
    }

    task_id = task_manager.create_task(
        keyword=keyword,
        max_count=result.summary["eligible_posts"],
        product="Comments",
        fetch_replies=True,
        max_replies_per_tweet=max_replies_per_tweet,
        reply_depth=reply_depth,
        crawl_strategy="bfs",
        platform=platform,
        task_kind="comment_backfill",
        source_file_name=source_file_name,
        comment_backfill_progress=progress,
    )
    task_manager.update_preview_tweets(task_id, 0, result.tweets)

    task = task_manager.get_task_summary(task_id)
    if not task:
        raise RuntimeError("评论补采任务创建失败")

    crawl_service.start_crawler_thread(
        task_id=task_id,
        task=task,
        resume=True,
    )
    refreshed = task_manager.get_task_summary(task_id) or task
    return CommentBackfillImportResponse(
        task=TaskOut(**refreshed),
        summary=CommentBackfillAnalyzeResponse(**result.summary),
    )
