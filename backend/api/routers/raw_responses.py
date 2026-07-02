"""
原始响应文件管理 API

提供查询和下载已保存的原始 SearchTimeline 响应文件的接口。
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from crawler.response_saver import (
    list_task_responses,
    list_all_tasks,
    delete_task_responses,
    get_task_response_dir,
    sweep_raw_responses,
)
from config import settings

router = APIRouter(prefix="/api/v1/raw-responses", tags=["raw-responses"])


@router.post("/sweep", summary="立即执行一次滚动清理")
async def sweep_now():
    """
    按当前清理策略（终态 TTL / 单任务大小 / 全局大小）立即清理归档。
    返回删除目录数、释放字节、剩余字节。仅清理终态任务，绝不删正在写入的目录。
    """
    return sweep_raw_responses(reason="manual")


@router.get("/", summary="列出所有已保存原始响应的任务")
async def get_all_tasks():
    """
    返回所有任务的归档摘要，包括：
    - task_id
    - 已保存的页数
    - 总文件大小（字节）
    - 最后保存时间
    """
    tasks = list_all_tasks()
    from config import resolve_data_path
    return {
        "save_enabled": settings.save_raw_responses,
        "max_pages_per_task": settings.raw_responses_max_pages,
        "storage_dir": str(resolve_data_path(settings.raw_responses_dir).resolve()),
        "tasks": tasks,
    }


@router.delete("/all", summary="删除全部任务的原始响应文件")
async def delete_all_task_files():
    """删除全部任务原始响应目录。"""
    tasks = list_all_tasks()
    deleted_files = 0
    deleted_tasks = 0
    for task in tasks:
        task_id = task.get("task_id", "")
        if not task_id:
            continue
        count = delete_task_responses(task_id)
        if count > 0:
            deleted_tasks += 1
            deleted_files += count
    return {"deleted_tasks": deleted_tasks, "deleted_files": deleted_files}


@router.get("/{task_id}", summary="列出某任务的所有原始响应文件")
async def get_task_files(task_id: str):
    """返回指定任务目录下所有 JSON 文件的列表（文件名、大小、保存时间）"""
    files = list_task_responses(task_id)
    return {
        "task_id": task_id,
        "file_count": len(files),
        "files": files,
    }


@router.get("/{task_id}/{filename}", summary="下载某个原始响应文件")
async def download_response_file(task_id: str, filename: str):
    """
    下载指定任务下的某个原始响应 JSON 文件。
    文件名格式：page_{页码}_{时间戳}.json
    """
    # 安全校验：只允许 page_*.json 格式，防止路径穿透
    if not filename.startswith("page_") or not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="非法文件名")

    task_dir = get_task_response_dir(task_id)
    file_path = task_dir / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"文件不存在: task_id={task_id}, filename={filename}",
        )

    return FileResponse(
        path=str(file_path),
        media_type="application/json",
        filename=filename,
    )


@router.delete("/{task_id}", summary="删除某任务的所有原始响应文件")
async def delete_task_files(task_id: str):
    """删除指定任务目录及其下所有原始响应文件"""
    count = delete_task_responses(task_id)
    return {"task_id": task_id, "deleted_files": count}
