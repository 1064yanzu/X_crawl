"""
任务管理路由
GET    /api/v1/tasks           查看所有任务列表
DELETE /api/v1/tasks/{task_id} 删除任务记录
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
