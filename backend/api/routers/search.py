"""
搜索路由（v4 - 使用统一线程启动入口）
"""
from fastapi import APIRouter, HTTPException
from api.schemas.task import SearchRequest, TaskOut
from api.services import task_manager, crawl_service
from config import settings

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
    active_count = task_manager.count_active_tasks()
    limit = max(1, int(settings.crawler_max_concurrent_tasks))
    if active_count >= limit:
        raise HTTPException(
            status_code=409,
            detail=f"当前运行任务数已达上限（{limit}），请等待任务完成或暂停后再新建任务",
        )

    task_id = task_manager.create_task(
        keyword=req.keyword,
        max_count=req.max_count,
        product=req.product,
        task_id=req.task_id if req.resume and req.task_id else None,
        fetch_replies=req.fetch_replies,
        max_replies_per_tweet=req.max_replies_per_tweet,
        crawl_strategy=req.crawl_strategy,
    )
    task_data = task_manager.get_task(task_id)
    # 使用统一的线程启动入口
    crawl_service.start_crawler_thread(
        task_id=task_id,
        task=task_data,
        resume=req.resume,
    )
    return TaskOut(**task_data)


@router.get(
    "/{task_id}",
    response_model=TaskOut,
    summary="查询搜索任务状态与结果",
)
async def get_search_task(task_id: str) -> TaskOut:
    task_data = task_manager.get_task(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return TaskOut(**task_data)
