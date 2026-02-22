"""
任务管理路由（v2 - 新增 pause/resume/stop 控制接口）
GET    /api/v1/tasks           查看所有任务列表
DELETE /api/v1/tasks/{task_id} 删除任务记录
POST   /api/v1/tasks/{task_id}/pause  暂停任务
POST   /api/v1/tasks/{task_id}/resume 继续任务
POST   /api/v1/tasks/{task_id}/stop   主动终止任务
"""
from fastapi import APIRouter, HTTPException
from api.schemas.task import TaskOut
from api.services import task_manager

router = APIRouter(prefix="/api/v1/tasks", tags=["任务管理"])


@router.get(
    "",
    response_model=list[TaskOut],
    summary="获取所有任务列表",
    description="返回所有历史任务，按创建时间倒序排列。",
)
async def list_tasks() -> list[TaskOut]:
    """获取全部任务列表"""
    tasks = task_manager.list_tasks()
    return [TaskOut(**t) for t in tasks]


@router.delete(
    "/{task_id}",
    summary="删除任务记录",
    description="删除指定的任务记录（不影响正在运行的爬虫进程）。",
)
async def delete_task(task_id: str) -> dict:
    """删除任务"""
    success = task_manager.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return {"message": f"任务 {task_id} 已删除"}


@router.post(
    "/{task_id}/pause",
    summary="暂停任务",
    description="向正在运行的任务发送暂停信号，爬虫将在下一次翻页前停下来等待。",
)
async def pause_task(task_id: str) -> dict:
    """暂停指定任务"""
    success = task_manager.pause_task(task_id)
    if not success:
        task = task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        raise HTTPException(
            status_code=409,
            detail=f"任务当前状态为 '{task['status']}'，无法暂停（仅运行中任务可暂停）",
        )
    return {"message": f"任务 {task_id} 暂停信号已发送", "status": "paused"}


@router.post(
    "/{task_id}/resume",
    summary="继续任务",
    description="唤醒已暂停的任务，爬虫将从暂停位置继续爬取。",
)
async def resume_task(task_id: str) -> dict:
    """继续指定任务"""
    success = task_manager.resume_task(task_id)
    if not success:
        task = task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        raise HTTPException(
            status_code=409,
            detail=f"任务当前状态为 '{task['status']}'，无法继续（仅已暂停任务可继续）",
        )
    return {"message": f"任务 {task_id} 继续信号已发送", "status": "running"}


@router.post(
    "/{task_id}/stop",
    summary="主动终止任务",
    description=(
        "向任务发送终止信号，爬虫将在下一次翻页前停止，"
        "已爬取的数据将被保留。终止后任务状态变为 `stopped`，"
        "区别于异常 `failed` 状态。"
    ),
)
async def stop_task(task_id: str) -> dict:
    """主动终止指定任务"""
    success = task_manager.stop_task(task_id)
    if not success:
        task = task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        raise HTTPException(
            status_code=409,
            detail=f"任务当前状态为 '{task['status']}'，无法终止（仅运行中/已暂停/等待中任务可终止）",
        )
    return {"message": f"任务 {task_id} 终止信号已发送", "status": "stopping"}
