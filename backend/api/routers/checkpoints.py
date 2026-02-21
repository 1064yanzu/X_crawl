"""
断点续爬检查点管理路由
GET    /api/v1/checkpoints         列出所有可恢复的检查点
DELETE /api/v1/checkpoints/{task_id}  删除检查点文件
"""
from fastapi import APIRouter, HTTPException
from crawler.checkpoint import list_checkpoints, delete_checkpoint
from api.schemas.task import CheckpointInfo

router = APIRouter(prefix="/api/v1/checkpoints", tags=["断点续爬"])


@router.get(
    "",
    response_model=list[CheckpointInfo],
    summary="列出所有可恢复的检查点",
    description=(
        "返回所有磁盘上存在的爬取检查点，按保存时间倒序。\n"
        "`can_resume=true` 表示该检查点有 next_cursor，可以继续爬取。\n"
        "使用 `POST /api/v1/search` 并传入对应的 `task_id` + `resume=true` 恢复爬取。"
    ),
)
async def get_checkpoints() -> list[CheckpointInfo]:
    return [CheckpointInfo(**c) for c in list_checkpoints()]


@router.delete(
    "/{task_id}",
    summary="删除指定检查点",
)
async def remove_checkpoint(task_id: str) -> dict:
    delete_checkpoint(task_id)
    return {"message": f"检查点 {task_id} 已删除"}
