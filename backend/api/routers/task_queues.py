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
