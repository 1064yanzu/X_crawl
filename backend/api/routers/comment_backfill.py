from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from api.schemas.comment_backfill import (
    CommentBackfillAnalyzeResponse,
    CommentBackfillFromTasksRequest,
    CommentBackfillFromTasksResponse,
    CommentBackfillImportResponse,
    CommentBackfillTaskSourceSummary,
)
from api.schemas.task import TaskOut
from api.schemas.task_queue import TaskQueueOut
from api.services import crawl_service, task_manager, task_queue_manager
from api.services.comment_backfill_importer import analyze_comment_backfill_file
from api.services.comment_backfill_task_source import analyze_comment_backfill_task

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


@router.post(
    "/from-tasks",
    response_model=CommentBackfillFromTasksResponse,
    summary="从已完成任务直接创建评论补采任务",
)
async def create_comment_backfill_from_tasks(
    req: CommentBackfillFromTasksRequest,
) -> CommentBackfillFromTasksResponse:
    ordered_task_ids: list[str] = []
    seen_ids: set[str] = set()
    for task_id in req.task_ids:
        normalized = task_id.strip()
        if normalized and normalized not in seen_ids:
            seen_ids.add(normalized)
            ordered_task_ids.append(normalized)

    sources: list[CommentBackfillTaskSourceSummary] = []
    queue_payloads: list[dict] = []

    for task_id in ordered_task_ids:
        task = task_manager.get_task_full(task_id)
        if not task:
            sources.append(
                CommentBackfillTaskSourceSummary(
                    source_task_id=task_id,
                    source_keyword="",
                    platform="x",
                    task_status="missing",
                    result_count=0,
                    unique_post_count=0,
                    eligible_posts=0,
                    status="skipped",
                    reason="任务不存在",
                )
            )
            continue

        try:
            analysis = analyze_comment_backfill_task(task)
        except HTTPException as exc:
            sources.append(
                CommentBackfillTaskSourceSummary(
                    source_task_id=task_id,
                    source_keyword=str(task.get("keyword") or ""),
                    platform=task.get("platform") or "x",
                    task_status=str(task.get("status") or ""),
                    result_count=int(task.get("result_count") or 0),
                    unique_post_count=0,
                    eligible_posts=0,
                    status="skipped",
                    reason=str(getattr(exc, "detail", exc)),
                )
            )
            continue

        summary = dict(analysis.summary)
        if summary["eligible_posts"] <= 0:
            sources.append(
                CommentBackfillTaskSourceSummary(
                    **summary,
                    status="skipped",
                    reason="当前任务没有可补采评论的帖子（可能已抓过评论、评论数为 0，或缺少关键字段）",
                )
            )
            continue

        platform = summary["platform"]
        platform_label = "X" if platform == "x" else "微博"
        queue_payloads.append(
            {
                "keyword": f"{platform_label} 评论补采 · {summary['source_keyword'] or summary['source_task_id'][:8]}",
                "max_count": summary["eligible_posts"],
                "product": "Comments",
                "fetch_replies": True,
                "max_replies_per_tweet": req.max_replies_per_tweet,
                "reply_depth": req.reply_depth,
                "crawl_strategy": "bfs",
                "platform": platform,
                "task_kind": "comment_backfill",
                "source_file_name": None,
                "comment_backfill_progress": {
                    "total_posts": summary["unique_post_count"],
                    "eligible_posts": summary["eligible_posts"],
                    "processed_posts": 0,
                    "skipped_posts": max(0, summary["unique_post_count"] - summary["eligible_posts"]),
                    "succeeded_posts": 0,
                    "failed_posts": 0,
                },
                "seed_tweets": analysis.tweets,
                "source_task_id": summary["source_task_id"],
            }
        )
        sources.append(CommentBackfillTaskSourceSummary(**summary, status="created"))

    if not queue_payloads:
        raise HTTPException(status_code=400, detail="所选任务中没有可直接补采评论的已完成任务")

    if len(queue_payloads) == 1:
        payload = queue_payloads[0]
        task_id = task_manager.create_task(
            keyword=payload["keyword"],
            max_count=payload["max_count"],
            product=payload["product"],
            fetch_replies=payload["fetch_replies"],
            max_replies_per_tweet=payload["max_replies_per_tweet"],
            reply_depth=payload["reply_depth"],
            crawl_strategy=payload["crawl_strategy"],
            platform=payload["platform"],
            task_kind=payload["task_kind"],
            source_file_name=payload["source_file_name"],
            comment_backfill_progress=payload["comment_backfill_progress"],
        )
        task_manager.update_preview_tweets(task_id, 0, payload["seed_tweets"])
        task = task_manager.get_task_summary(task_id)
        if not task:
            raise HTTPException(status_code=500, detail="评论补采任务创建失败")
        crawl_service.start_crawler_thread(task_id=task_id, task=task, resume=True)
        refreshed = task_manager.get_task_summary(task_id) or task

        for index, source in enumerate(sources):
            if source.status == "created":
                sources[index] = source.model_copy(update={"created_task_id": task_id})
                break

        return CommentBackfillFromTasksResponse(
            created_count=1,
            queued=False,
            tasks=[TaskOut(**refreshed)],
            sources=sources,
        )

    queue_name = (req.queue_name or "").strip() or "评论补采批次"
    queue = task_queue_manager.create_queue(name=queue_name, task_payloads=queue_payloads)
    created_tasks = [TaskOut(**task) for task in queue.get("tasks", [])]
    created_task_ids = [task.task_id for task in created_tasks]
    created_index = 0
    updated_sources: list[CommentBackfillTaskSourceSummary] = []
    for source in sources:
        if source.status == "created" and created_index < len(created_task_ids):
            updated_sources.append(
                source.model_copy(update={"created_task_id": created_task_ids[created_index]})
            )
            created_index += 1
        else:
            updated_sources.append(source)

    return CommentBackfillFromTasksResponse(
        created_count=len(created_tasks),
        queued=True,
        queue=TaskQueueOut(**queue),
        tasks=created_tasks,
        sources=updated_sources,
    )
