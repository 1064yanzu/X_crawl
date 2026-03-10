"""
任务管理路由（v3 - 使用统一线程启动入口）
GET    /api/v1/tasks           查看所有任务列表
DELETE /api/v1/tasks/{task_id} 删除任务记录
POST   /api/v1/tasks/{task_id}/pause  暂停任务
POST   /api/v1/tasks/{task_id}/resume 继续任务
POST   /api/v1/tasks/{task_id}/stop   主动终止任务
GET    /api/v1/tasks/{task_id}/stream SSE 实时事件流
"""
import asyncio
import json
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from api.schemas.task import TaskOut
from api.services import task_manager, crawl_service
from config import settings

router = APIRouter(prefix="/api/v1/tasks", tags=["任务管理"])


def _stream_snapshot(task: dict) -> dict:
    """
    SSE 仅推送轻量快照，避免长连接下反复传输全量 tweets。
    preview_tweets 保留（条数受 crawler_preview_count 限制）。
    """
    payload = dict(task)
    payload["tweets"] = []
    preview = payload.get("preview_tweets") or []
    if isinstance(preview, list):
        limit = max(1, int(getattr(settings, "crawler_preview_count", 10)))
        payload["preview_tweets"] = preview[-limit:]
    else:
        payload["preview_tweets"] = []
    return payload


@router.get(
    "",
    response_model=list[TaskOut],
    summary="获取所有任务列表",
    description="返回所有历史任务，按创建时间倒序排列。",
)
async def list_tasks(
    include_payload: bool = Query(
        default=False,
        description="是否返回 tweets/preview_tweets。默认 false 仅返回摘要，减少轮询开销。",
    ),
) -> list[TaskOut]:
    """获取全部任务列表（支持摘要模式）"""
    tasks = task_manager.list_tasks(include_payload=include_payload)
    if not include_payload:
        for task in tasks:
            task["preview_tweets"] = []
    return [TaskOut(**t) for t in tasks]


@router.get(
    "/{task_id}/stream",
    summary="任务实时事件流（SSE）",
    description="通过 Server-Sent Events 持续推送任务实时快照与动作事件。",
)
async def stream_task(task_id: str, request: Request):
    existing = task_manager.get_task_summary(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    interval_ms = max(200, min(5000, int(settings.crawler_live_push_interval_ms)))

    async def event_generator():
        last_event_id = 0
        last_snapshot_sent = 0.0
        last_heartbeat = time.monotonic()

        while True:
            if await request.is_disconnected():
                break

            task = task_manager.get_task_summary(task_id)
            if not task:
                payload = json.dumps({"task_id": task_id, "type": "closed"}, ensure_ascii=False)
                yield f"event: closed\ndata: {payload}\n\n"
                break

            events = task_manager.get_task_events(task_id, after_id=last_event_id, limit=120)
            for event in events:
                last_event_id = max(last_event_id, int(event.get("id", 0)))
                payload = json.dumps(event, ensure_ascii=False)
                yield f"event: action\ndata: {payload}\n\n"

            now = time.monotonic()
            if now - last_snapshot_sent >= interval_ms / 1000.0:
                payload = json.dumps(_stream_snapshot(task), ensure_ascii=False)
                yield f"event: snapshot\ndata: {payload}\n\n"
                last_snapshot_sent = now

            if now - last_heartbeat >= 15.0:
                hb = json.dumps({"ts": int(now), "task_id": task_id}, ensure_ascii=False)
                yield f"event: heartbeat\ndata: {hb}\n\n"
                last_heartbeat = now

            await asyncio.sleep(interval_ms / 1000.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
        task = task_manager.get_task_summary(task_id)
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
    description=(
        "恢复任务爬取。支持以下场景：\n"
        "- **已暂停 (paused)**：唤醒暂停中的爬虫，从暂停位置继续\n"
        "- **已完成/已终止/已失败 (done/stopped/failed)**：重启爬虫线程，从断点继续爬取\n"
        "若爬虫线程已死（浏览器被关闭等），会自动重启爬虫线程。"
    ),
)
async def resume_task(task_id: str) -> dict:
    """继续指定任务（支持已暂停和已结束的任务）"""
    task = task_manager.get_task_summary(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    status = task["status"]

    # ── 已结束的任务：重启爬虫线程从断点恢复 ──
    if status in ("done", "stopped", "failed"):
        success = task_manager.resume_finished_task(task_id)
        if not success:
            raise HTTPException(status_code=409, detail=f"任务恢复失败: {task_id}")
        crawl_service.start_crawler_thread(task_id, task, force_new_browser=True)
        return {"message": f"任务 {task_id} 已恢复并加入调度队列", "status": "pending"}

    # ── 已暂停的任务：唤醒或重启 ──
    current_signal = task_manager.get_signal(task_id)
    if status not in ("paused",) and current_signal != "pause":
        raise HTTPException(
            status_code=409,
            detail=f"任务当前状态为 '{status}'，无法继续",
        )

    if task_manager.is_thread_alive(task_id):
        # 爬虫线程还活着，只需发送 run 信号即可唤醒轮询
        task_manager.resume_task(task_id)
        return {"message": f"任务 {task_id} 继续信号已发送", "status": "running"}
    else:
        # 爬虫线程已死（浏览器被关闭等），重新入队从断点恢复
        task_manager.resume_task(task_id)
        crawl_service.start_crawler_thread(task_id, task, force_new_browser=True)
        return {"message": f"任务 {task_id} 已重新加入调度队列，从断点恢复", "status": "pending"}


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
        task = task_manager.get_task_summary(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        raise HTTPException(
            status_code=409,
            detail=f"任务当前状态为 '{task['status']}'，无法终止（仅运行中/已暂停/等待中任务可终止）",
        )
    return {"message": f"任务 {task_id} 终止信号已发送", "status": "stopping"}
