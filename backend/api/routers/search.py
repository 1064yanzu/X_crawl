"""
搜索路由（v5 - 调度器队列化执行）
"""
from fastapi import APIRouter, HTTPException, Query
from api.schemas.task import SearchRequest, TaskOut
from api.services import task_manager, crawl_service

router = APIRouter(prefix="/api/v1/search", tags=["搜索"])


@router.post(
    "",
    response_model=TaskOut,
    summary="发起搜索任务",
    description=(
        "创建推文搜索任务，后台异步执行，立即返回 `task_id`。\n\n"
        "**断点续爬**：若之前的任务因网络/浏览器问题中断，可携带原 `task_id` 和 `resume=true` 恢复爬取，"
        "已爬取的推文不会丢失。\n\n"
        "**回复抓取**：设置 `fetch_replies=true` 可抓取每条推文的评论回复。\n\n"
        "**策略选择**：`crawl_strategy=bfs`（广度优先，先爬完所有搜索页再抓回复）"
        "或 `dfs`（深度优先，每条推文搜到后立即抓其回复）。\n\n"
        "可通过 `GET /api/v1/checkpoints` 查看可恢复的检查点列表。"
    ),
)
async def create_search_task(
    req: SearchRequest,
) -> TaskOut:
    task_id = task_manager.create_task(
        keyword=req.keyword,
        product=req.product,
        task_id=req.task_id if req.resume and req.task_id else None,
        fetch_replies=req.fetch_replies,
        max_replies_per_tweet=req.max_replies_per_tweet,
        reply_depth=req.reply_depth,
        crawl_strategy=req.crawl_strategy,
        platform=req.platform,
        start_date=req.start_date,
        end_date=req.end_date,
    )
    task_data = task_manager.get_task_summary(task_id)
    if not task_data:
        raise HTTPException(status_code=500, detail="任务创建失败")

    # 统一调度入口：先入队，再由调度器按并发上限执行
    crawl_service.start_crawler_thread(
        task_id=task_id,
        task=task_data,
        resume=req.resume,
    )
    refreshed = task_manager.get_task_summary(task_id) or task_data
    return TaskOut(**refreshed)


@router.get(
    "/{task_id}",
    response_model=TaskOut,
    summary="查询搜索任务状态与结果",
)
async def get_search_task(
    task_id: str,
    include_tweets: bool = Query(
        default=True,
        description="是否返回完整 tweets 列表。轮询建议 false，减少传输开销。",
    ),
) -> TaskOut:
    if include_tweets:
        task_data = task_manager.get_task_full(task_id)
    else:
        task_data = task_manager.get_task_summary(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return TaskOut(**task_data)
