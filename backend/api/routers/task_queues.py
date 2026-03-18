from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.task_queue import TaskQueueCreateRequest, TaskQueueOut
from api.services import task_queue_manager

router = APIRouter(prefix="/api/v1/task-queues", tags=["任务队列"])


@router.post(
    "",
    response_model=TaskQueueOut,
    summary="创建顺序任务队列",
    description="一次性创建多个采集任务，并按配置顺序一个接一个执行。",
)
async def create_task_queue(req: TaskQueueCreateRequest) -> TaskQueueOut:
    queue = task_queue_manager.create_queue(
        name=req.name,
        task_payloads=[item.model_dump() for item in req.tasks],
    )
    return TaskQueueOut(**queue)


@router.get(
    "",
    response_model=list[TaskQueueOut],
    summary="查看任务队列列表",
)
async def list_task_queues() -> list[TaskQueueOut]:
    queues = task_queue_manager.list_queues()
    return [TaskQueueOut(**queue) for queue in queues]


@router.get(
    "/{queue_id}",
    response_model=TaskQueueOut,
    summary="查看单个任务队列",
)
async def get_task_queue(queue_id: str) -> TaskQueueOut:
    queue = task_queue_manager.get_queue(queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail=f"任务队列不存在: {queue_id}")
    return TaskQueueOut(**queue)


@router.post(
    "/{queue_id}/resume",
    summary="恢复整个任务队列",
    description=(
        "一次性恢复队列中所有暂停/停止/失败的任务并提交给调度器。"
        "调度器根据并发上限自行控制哪些任务立即执行、哪些排队。"
    ),
)
async def resume_task_queue(queue_id: str) -> dict:
    try:
        result = task_queue_manager.resume_queue(queue_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    total_resumed = len(result["resumed"])
    total_running = len(result["already_running"])
    return {
        "message": f"队列已恢复：{total_resumed} 个任务重新提交调度器，{total_running} 个已在运行",
        **result,
    }
