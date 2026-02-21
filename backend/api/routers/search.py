"""
搜索路由（升级版）
支持断点续爬：通过 resume=true + task_id 恢复已中断的爬取任务
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException
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
        "可通过 `GET /api/v1/checkpoints` 查看可恢复的检查点列表。"
    ),
)
async def create_search_task(
    req: SearchRequest,
    background_tasks: BackgroundTasks,
) -> TaskOut:
    # 若指定了 task_id 且 resume=True，复用已有任务（断点续爬）
    task_id = task_manager.create_task(
        keyword=req.keyword,
        max_count=req.max_count,
        product=req.product,
        task_id=req.task_id if req.resume and req.task_id else None,
    )
    background_tasks.add_task(
        crawl_service.run_search_task,
        task_id=task_id,
        keyword=req.keyword,
        max_count=req.max_count,
        product=req.product,
        resume=req.resume,
    )
    task_data = task_manager.get_task(task_id)
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
