"""
任务管理路由（v3 - 使用统一线程启动入口）
GET    /api/v1/tasks                  查看所有任务列表
POST   /api/v1/tasks/resume-all       一键恢复所有暂停/停止/失败的任务
DELETE /api/v1/tasks/{task_id}        删除任务记录
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
from api.services import task_manager, crawl_service, task_queue_manager
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


@router.post(
    "/resume-all",
    summary="一键恢复所有可恢复的任务",
    description=(
        "一次性恢复所有暂停/停止/失败的任务。"
        "对于队列中的任务，会自动通过队列恢复；"
        "对于独立任务，会逐个调用恢复逻辑。\n\n"
        "返回恢复成功、跳过、失败的任务 ID 列表。"
    ),
)
async def resume_all_tasks() -> dict:
    """一键恢复所有暂停/停止/失败的任务"""
    import logging
    _logger = logging.getLogger(__name__)

    all_tasks = task_manager.list_tasks(include_payload=False)
    resumable_statuses = {"paused", "stopped", "failed"}
    queue_task_map: dict[str, list[dict]] = {}

    for task in all_tasks:
        queue_id = task.get("queue_id")
        if queue_id:
            queue_task_map.setdefault(queue_id, []).append(task)

    resumed_ids: list[str] = []
    skipped_ids: list[str] = []
    failed_ids: list[str] = []
    already_running_ids: list[str] = []
    processed_queue_ids: set[str] = set()

    for task in all_tasks:
        task_id = task.get("task_id", "")
        status = task.get("status", "")

        if status in ("running", "pending"):
            already_running_ids.append(task_id)
            continue

        if status not in resumable_statuses:
            skipped_ids.append(task_id)
            continue

        # 如果属于队列，通过队列批量恢复（避免重复操作）
        queue_id = task.get("queue_id")
        if queue_id and queue_id not in processed_queue_ids:
            processed_queue_ids.add(queue_id)
            try:
                result = task_queue_manager.resume_queue(queue_id)
                resumed_ids.extend(result.get("resumed", []))
                already_running_ids.extend(result.get("already_running", []))
                _logger.info(
                    "resume_all: queue=%s resumed=%d, already_running=%d",
                    queue_id[:8], len(result.get("resumed", [])), len(result.get("already_running", [])),
                )
            except Exception as e:
                _logger.error("resume_all: queue=%s 恢复失败: %s", queue_id[:8], e, exc_info=True)
                failed_ids.extend(
                    queued_task.get("task_id", "")
                    for queued_task in queue_task_map.get(queue_id, [])
                    if queued_task.get("status") in resumable_statuses
                )
            continue
        elif queue_id and queue_id in processed_queue_ids:
            # 该队列已处理过，跳过
            continue

        # 独立任务：逐个恢复
        try:
            if status in ("done", "stopped", "failed"):
                success = task_manager.resume_finished_task(task_id)
                if success:
                    crawl_service.start_crawler_thread(task_id, task, force_new_browser=True)
                    resumed_ids.append(task_id)
                else:
                    failed_ids.append(task_id)
            elif status == "paused":
                if task_manager.is_thread_alive(task_id):
                    task_manager.resume_task(task_id)
                else:
                    task_manager.resume_task(task_id)
                    crawl_service.start_crawler_thread(task_id, task, force_new_browser=True)
                resumed_ids.append(task_id)
        except Exception as e:
            _logger.error("resume_all: task=%s 恢复失败: %s", task_id[:8], e, exc_info=True)
            failed_ids.append(task_id)

    # 去重（队列恢复可能已包含某些 task_id）
    resumed_ids = list(dict.fromkeys(resumed_ids))
    skipped_ids = list(dict.fromkeys(task_id for task_id in skipped_ids if task_id))
    failed_ids = list(dict.fromkeys(task_id for task_id in failed_ids if task_id))
    already_running_ids = list(dict.fromkeys(task_id for task_id in already_running_ids if task_id))

    _logger.info(
        "resume_all 完成: resumed=%d, already_running=%d, skipped=%d, failed=%d",
        len(resumed_ids), len(already_running_ids), len(skipped_ids), len(failed_ids),
    )
    return {
        "message": f"已恢复 {len(resumed_ids)} 个任务",
        "resumed": resumed_ids,
        "already_running": already_running_ids,
        "skipped": skipped_ids,
        "failed": failed_ids,
    }


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
    task_queue_manager.mark_task_paused(task_id)
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
    """继续指定任务（支持已暂停和已结束的任务）。
    并发模式下，如果该任务属于队列，会自动恢复同队列其他暂停/停止的任务。
    """
    task = task_manager.get_task_summary(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    status = task["status"]
    can_resume, reason, needs_queue = task_queue_manager.can_resume_task(task_id)
    if not can_resume:
        raise HTTPException(status_code=409, detail=reason or "当前任务不允许继续")

    # ── 已结束的任务：重启爬虫线程从断点恢复 ──
    if status in ("done", "stopped", "failed"):
        success = task_manager.resume_finished_task(task_id)
        if not success:
            raise HTTPException(status_code=409, detail=f"任务恢复失败: {task_id}")
        if needs_queue:
            task_queue_manager.enqueue_resumed_task(task_id)
            return {"message": f"任务 {task_id} 已恢复并加入队列排队等待", "status": "pending"}
        task_queue_manager.mark_task_resuming(task_id)
        crawl_service.start_crawler_thread(task_id, task, force_new_browser=True)
        # 并发模式：自动恢复同队列其他任务
        _auto_resume_queue_siblings(task)
        return {"message": f"任务 {task_id} 已恢复并加入调度队列", "status": "pending"}

    # ── 已暂停的任务：唤醒或重启 ──
    current_signal = task_manager.get_signal(task_id)
    if status not in ("paused",) and current_signal != "pause":
        raise HTTPException(
            status_code=409,
            detail=f"任务当前状态为 '{status}'，无法继续",
        )

    if needs_queue:
        if task_manager.is_thread_alive(task_id):
            task_manager.send_signal(task_id, "stop")
        task_manager.resume_finished_task(task_id)
        task_queue_manager.enqueue_resumed_task(task_id)
        return {"message": f"任务 {task_id} 已恢复并加入队列排队等待", "status": "pending"}

    if task_manager.is_thread_alive(task_id):
        task_manager.resume_task(task_id)
        task_queue_manager.mark_task_resuming(task_id)
        # 并发模式：自动恢复同队列其他任务
        _auto_resume_queue_siblings(task)
        return {"message": f"任务 {task_id} 继续信号已发送", "status": "running"}
    else:
        task_manager.resume_task(task_id)
        task_queue_manager.mark_task_resuming(task_id)
        crawl_service.start_crawler_thread(task_id, task, force_new_browser=True)
        # 并发模式：自动恢复同队列其他任务
        _auto_resume_queue_siblings(task)
        return {"message": f"任务 {task_id} 已重新加入调度队列，从断点恢复", "status": "pending"}


def _auto_resume_queue_siblings(task: dict) -> None:
    """并发模式下，自动恢复同队列中其他暂停/停止的任务。"""
    import logging
    from config import settings
    _logger = logging.getLogger(__name__)
    max_concurrent = int(settings.crawler_max_concurrent_tasks)
    if max_concurrent <= 1:
        return
    queue_id = task.get("queue_id")
    if not queue_id:
        _logger.debug("_auto_resume_queue_siblings: task 无 queue_id，跳过")
        return
    try:
        result = task_queue_manager.resume_queue(queue_id)
        _logger.info(
            "_auto_resume_queue_siblings: queue=%s, resumed=%s, already_running=%s, skipped=%s",
            queue_id, result["resumed"], result["already_running"], result["skipped"],
        )
    except Exception as e:
        _logger.error("_auto_resume_queue_siblings 失败: queue=%s, error=%s", queue_id, e, exc_info=True)


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
