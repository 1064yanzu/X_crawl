"""
任务管理路由（v4 - 新增一键暂停/智能恢复）
GET    /api/v1/tasks                  查看所有任务列表
POST   /api/v1/tasks/pause-all        一键暂停所有活跃任务
POST   /api/v1/tasks/resume-all       智能恢复任务（区分用户暂停/风控暂停）
DELETE /api/v1/tasks/{task_id}        删除任务记录
POST   /api/v1/tasks/{task_id}/pause  暂停任务
POST   /api/v1/tasks/{task_id}/resume 继续任务
POST   /api/v1/tasks/{task_id}/stop   主动终止任务
GET    /api/v1/tasks/{task_id}/stream SSE 实时事件流
"""
import asyncio
import json
import re
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from api.schemas.task import (
    TaskOut,
    MergePreviewRequest,
    MergePreviewResponse,
    MergeRequest,
    MergeResponse,
    BatchUpdateReplyCollectionRequest,
    BatchUpdateReplyCollectionResponse,
)
from api.services import task_manager, crawl_service, task_queue_manager
from api.services import merge_service, task_reply_collection_service
from config import settings

router = APIRouter(prefix="/api/v1/tasks", tags=["任务管理"])


def _strip_weibo_time_syntax(keyword: str) -> str:
    text = re.sub(r"\s+", " ", (keyword or "").strip())
    text = re.sub(r"\bsince:\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\buntil:\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
    "/pause-all",
    summary="一键暂停所有活跃任务",
    description=(
        "暂停所有正在运行和等待中的任务。\n\n"
        "- **running** 任务 → 发送暂停信号，状态变为 `paused`\n"
        "- **pending** 任务 → 发送终止信号，状态变为 `stopped`\n\n"
        "返回各类操作的任务 ID 列表。"
    ),
)
async def pause_all_tasks() -> dict:
    """一键暂停所有活跃任务（running → paused, pending → stopped）"""
    import logging
    _logger = logging.getLogger(__name__)

    all_tasks = task_manager.list_tasks(include_payload=False)

    paused_ids: list[str] = []
    stopped_ids: list[str] = []
    skipped_ids: list[str] = []
    failed_ids: list[str] = []

    for task in all_tasks:
        task_id = task.get("task_id", "")
        status = task.get("status", "")

        if status == "running":
            try:
                success = task_manager.pause_task(task_id)
                if success:
                    task_queue_manager.mark_task_paused(task_id)
                    paused_ids.append(task_id)
                else:
                    failed_ids.append(task_id)
            except Exception as e:
                _logger.error("pause_all: task=%s 暂停失败: %s", task_id[:8], e, exc_info=True)
                failed_ids.append(task_id)
        elif status == "pending":
            try:
                success = task_manager.stop_task(task_id)
                if success:
                    stopped_ids.append(task_id)
                else:
                    failed_ids.append(task_id)
            except Exception as e:
                _logger.error("pause_all: task=%s 停止失败: %s", task_id[:8], e, exc_info=True)
                failed_ids.append(task_id)
        else:
            skipped_ids.append(task_id)

    total_affected = len(paused_ids) + len(stopped_ids)
    _logger.info(
        "pause_all 完成: paused=%d, stopped=%d, skipped=%d, failed=%d",
        len(paused_ids), len(stopped_ids), len(skipped_ids), len(failed_ids),
    )
    return {
        "message": f"已暂停 {total_affected} 个任务",
        "paused": paused_ids,
        "stopped": stopped_ids,
        "skipped": skipped_ids,
        "failed": failed_ids,
    }


def _classify_resumable_tasks(
    all_tasks: list[dict],
) -> tuple[list[dict], list[dict]]:
    """将可恢复任务分为"用户主动暂停"和"风控暂停"两类。

    用户主动暂停：
      - status == "paused" 且 risk_state == "none"
      - status == "stopped"（程序重启中断 or 用户主动停止）
      - status == "failed" 且 risk_state == "none"
    风控暂停：
      - status in ("paused", "failed") 且 risk_state != "none"
    """
    user_paused: list[dict] = []
    risk_paused: list[dict] = []

    for task in all_tasks:
        status = task.get("status", "")
        risk_state = task.get("risk_state", "none")

        if status in ("running", "pending", "done"):
            continue

        # 风控导致的暂停/失败
        if risk_state != "none" and status in ("paused", "failed"):
            risk_paused.append(task)
            continue

        # 用户主动暂停
        if status == "paused" and risk_state == "none":
            user_paused.append(task)
            continue

        # 被程序重启中断停止的、或用户主动 stop 的
        if status == "stopped":
            user_paused.append(task)
            continue

        # 其余 failed（非风控），也归入用户暂停类
        if status == "failed" and risk_state == "none":
            user_paused.append(task)
            continue

    return user_paused, risk_paused


def _do_resume_tasks(
    target_tasks: list[dict],
    all_tasks: list[dict],
    _logger,
) -> tuple[list[str], list[str], list[str]]:
    """对目标任务执行恢复操作，返回 (resumed_ids, already_running_ids, failed_ids)。"""
    resumable_statuses = {"paused", "stopped", "failed"}
    queue_task_map: dict[str, list[dict]] = {}
    target_ids = {t.get("task_id", "") for t in target_tasks}

    for task in all_tasks:
        queue_id = task.get("queue_id")
        if queue_id:
            queue_task_map.setdefault(queue_id, []).append(task)

    resumed_ids: list[str] = []
    already_running_ids: list[str] = []
    failed_ids: list[str] = []
    processed_queue_ids: set[str] = set()

    for task in target_tasks:
        task_id = task.get("task_id", "")
        status = task.get("status", "")

        if status in ("running", "pending"):
            already_running_ids.append(task_id)
            continue

        if status not in resumable_statuses:
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
                    if queued_task.get("task_id", "") in target_ids
                    and queued_task.get("status") in resumable_statuses
                )
            continue
        elif queue_id and queue_id in processed_queue_ids:
            continue

        # 独立任务：逐个恢复（done 不参与一键恢复）
        try:
            if status in ("stopped", "failed"):
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

    return (
        list(dict.fromkeys(resumed_ids)),
        list(dict.fromkeys(tid for tid in already_running_ids if tid)),
        list(dict.fromkeys(tid for tid in failed_ids if tid)),
    )


@router.post(
    "/resume-all",
    summary="智能恢复所有可恢复的任务",
    description=(
        "智能检测当前任务状态，区分恢复场景：\n\n"
        "- **user_paused**：存在用户主动暂停的任务（配合一键暂停使用），仅恢复这些任务\n"
        "- **risk_control**：仅存在因风控暂停的任务，恢复并重试这些任务\n"
        "- **mixed**：两种都有，全部恢复\n\n"
        "返回恢复结果和触发的场景类型。"
    ),
)
async def resume_all_tasks() -> dict:
    """智能恢复任务：自动区分用户暂停 vs 风控暂停场景"""
    import logging
    _logger = logging.getLogger(__name__)

    all_tasks = task_manager.list_tasks(include_payload=False)
    user_paused, risk_paused = _classify_resumable_tasks(all_tasks)

    has_user = len(user_paused) > 0
    has_risk = len(risk_paused) > 0

    # 判断恢复场景
    if has_user and has_risk:
        scenario = "mixed"
        target_tasks = user_paused + risk_paused
    elif has_user:
        scenario = "user_paused"
        target_tasks = user_paused
    elif has_risk:
        scenario = "risk_control"
        target_tasks = risk_paused
    else:
        scenario = "none"
        target_tasks = []

    if not target_tasks:
        return {
            "message": "没有需要恢复的任务",
            "scenario": scenario,
            "resumed": [],
            "already_running": [],
            "skipped": [],
            "failed": [],
        }

    resumed_ids, already_running_ids, failed_ids = _do_resume_tasks(
        target_tasks, all_tasks, _logger,
    )

    # 计算跳过的（不在 target 中的可恢复状态任务）
    target_id_set = {t.get("task_id", "") for t in target_tasks}
    skipped_ids = list(dict.fromkeys(
        t.get("task_id", "")
        for t in all_tasks
        if t.get("task_id", "") not in target_id_set
        and t.get("status") not in ("running", "pending")
        and t.get("task_id")
    ))

    _logger.info(
        "resume_all 完成: scenario=%s, resumed=%d, already_running=%d, skipped=%d, failed=%d",
        scenario, len(resumed_ids), len(already_running_ids), len(skipped_ids), len(failed_ids),
    )
    return {
        "message": f"已恢复 {len(resumed_ids)} 个任务",
        "scenario": scenario,
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


def _do_recrawl_task(task_id: str) -> tuple[str | None, int, str | None, bool]:
    """增量复爬单个任务的核心逻辑。

    Returns:
        (new_task_id, exclude_count, error_message)
        - 成功时 error_message 为 None
        - 失败时 new_task_id 为 None
    """
    original = task_manager.get_task_summary(task_id)
    if not original:
        return None, 0, f"任务不存在: {task_id}", False

    if original["status"] not in ("done", "stopped", "failed"):
        return None, 0, f"仅已完成/已停止/已失败的任务可复爬，当前状态: {original['status']}", False

    root_source_task_id = original.get("source_task_id") or task_id
    source_task = task_manager.get_task_summary(root_source_task_id) if root_source_task_id != task_id else original
    if not source_task:
        source_task = original

    platform = source_task.get("platform", original.get("platform", "x"))

    # 加载原始推文 ID 用于增量去重
    original_tweets = task_manager._get_task_result_snapshot(root_source_task_id, load=True)
    exclude_ids = [
        str(t.get("id") or t.get("mid") or "").strip()
        for t in original_tweets
        if str(t.get("id") or t.get("mid") or "").strip()
    ]

    recrawl_keyword = source_task["keyword"]
    if platform == "weibo":
        recrawl_keyword = _strip_weibo_time_syntax(recrawl_keyword)

    prepared = task_manager.prepare_task_for_recrawl(
        root_source_task_id,
        keyword=recrawl_keyword,
        max_count=source_task["max_count"],
        product=source_task["product"],
        fetch_replies=source_task.get("fetch_replies", False),
        max_replies_per_tweet=source_task.get("max_replies_per_tweet", 20),
        reply_depth=source_task.get("reply_depth", 2),
        crawl_strategy=source_task.get("crawl_strategy", "dfs"),
        platform=platform,
        start_date=source_task.get("start_date"),
        end_date=source_task.get("end_date"),
        source_task_id=root_source_task_id,
        exclude_tweet_ids=exclude_ids,
    )
    if not prepared:
        return None, 0, "复爬任务准备失败", False

    existing_task = task_manager.get_task_summary(root_source_task_id)
    if not existing_task:
        return None, 0, "复爬任务读取失败", False

    crawl_service.start_crawler_thread(
        task_id=root_source_task_id,
        task=existing_task,
        resume=False,
    )

    return root_source_task_id, len(exclude_ids), None, True


@router.post(
    "/{task_id}/recrawl",
    summary="增量复爬任务",
    description=(
        "基于已完成的任务在原任务上执行增量复爬。\n\n"
        "- 自动回源到最初任务，避免复爬派生任务继续链式增长\n"
        "- 保留原始数据，并仅抓取原任务中尚未存在的新帖子\n"
        "- 自动排除原始任务中已有的推文，仅收集新增推文\n"
        "- 支持 `done / stopped / failed` 状态的任务"
    ),
)
async def recrawl_task(task_id: str) -> dict:
    """增量复爬：在原任务上重跑并排除已有推文"""
    target_task_id, exclude_count, error, reused_existing = _do_recrawl_task(task_id)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return {
        "message": f"复爬已在原任务上重跑，保留 {exclude_count} 条历史结果作为提速种子",
        "task_id": target_task_id,
        "source_task_id": task_id,
        "exclude_count": exclude_count,
        "reused_existing": reused_existing,
    }


from pydantic import BaseModel as _BaseModel, Field as _Field


class RecrawlBatchRequest(_BaseModel):
    task_ids: list[str] = _Field(description="要批量复爬的任务 ID 列表", min_length=1)


class BatchPauseRequest(_BaseModel):
    task_ids: list[str] = _Field(description="要批量暂停的任务 ID 列表", min_length=1)


class BatchResumeRequest(_BaseModel):
    task_ids: list[str] = _Field(description="要批量继续的任务 ID 列表", min_length=1)


@router.post(
    "/recrawl-batch",
    summary="批量增量复爬",
    description=(
        "批量对多个已完成任务执行增量复爬。\n\n"
        "- 每个任务都会回源到最初任务，并在原任务上重跑\n"
        "- 跳过不符合条件的任务（运行中、非 X 平台等）\n"
        "- 返回所有已启动复爬的任务 ID 和跳过/失败详情"
    ),
)
async def recrawl_batch(req: RecrawlBatchRequest) -> dict:
    """批量增量复爬：对多个任务回源并在原任务上重跑"""
    processed: list[dict] = []
    skipped: list[dict] = []

    for task_id in req.task_ids:
        target_task_id, exclude_count, error, reused_existing = _do_recrawl_task(task_id)
        if error:
            skipped.append({"task_id": task_id, "reason": error})
        else:
            processed.append({
                "source_task_id": task_id,
                "task_id": target_task_id,
                "exclude_count": exclude_count,
                "reused_existing": reused_existing,
            })

    return {
        "message": f"已处理 {len(processed)} 个复爬任务，跳过 {len(skipped)} 个",
        "processed": processed,
        "skipped": skipped,
    }


@router.post(
    "/batch-pause",
    summary="批量暂停选中任务",
    description=(
        "对指定的任务 ID 列表执行暂停操作。\n\n"
        "- **running** 任务 → 发送暂停信号，状态变为 `paused`\n"
        "- **pending** 任务 → 发送终止信号，状态变为 `stopped`\n"
        "- 其他状态任务 → 跳过\n\n"
        "返回各类操作的任务 ID 列表。"
    ),
)
async def batch_pause_tasks(req: BatchPauseRequest) -> dict:
    """批量暂停指定任务"""
    import logging
    _logger = logging.getLogger(__name__)

    paused_ids: list[str] = []
    stopped_ids: list[str] = []
    skipped_ids: list[str] = []
    failed_ids: list[str] = []

    for task_id in req.task_ids:
        task = task_manager.get_task_summary(task_id)
        if not task:
            skipped_ids.append(task_id)
            continue

        status = task.get("status", "")
        if status == "running":
            try:
                success = task_manager.pause_task(task_id)
                if success:
                    task_queue_manager.mark_task_paused(task_id)
                    paused_ids.append(task_id)
                else:
                    failed_ids.append(task_id)
            except Exception as e:
                _logger.error("batch_pause: task=%s 暂停失败: %s", task_id[:8], e)
                failed_ids.append(task_id)
        elif status == "pending":
            try:
                success = task_manager.stop_task(task_id)
                if success:
                    stopped_ids.append(task_id)
                else:
                    failed_ids.append(task_id)
            except Exception as e:
                _logger.error("batch_pause: task=%s 停止失败: %s", task_id[:8], e)
                failed_ids.append(task_id)
        else:
            skipped_ids.append(task_id)

    total_affected = len(paused_ids) + len(stopped_ids)
    return {
        "message": f"已暂停 {total_affected} 个任务",
        "paused": paused_ids,
        "stopped": stopped_ids,
        "skipped": skipped_ids,
        "failed": failed_ids,
    }


@router.post(
    "/batch-resume",
    summary="批量继续选中任务",
    description=(
        "对指定的任务 ID 列表执行恢复操作。\n\n"
        "- **paused** 任务 → 唤醒暂停中的爬虫继续\n"
        "- **stopped / failed** 任务 → 重启爬虫线程从断点恢复\n"
        "- 其他状态任务 → 跳过\n\n"
        "返回各类操作的任务 ID 列表。"
    ),
)
async def batch_resume_tasks(req: BatchResumeRequest) -> dict:
    """批量继续指定任务"""
    import logging
    _logger = logging.getLogger(__name__)

    all_tasks = task_manager.list_tasks(include_payload=False)
    target_tasks = [t for t in all_tasks if t.get("task_id", "") in set(req.task_ids)]

    resumed_ids, already_running_ids, failed_ids = _do_resume_tasks(
        target_tasks, all_tasks, _logger,
    )

    requested_ids = set(req.task_ids)
    acted_ids = set(resumed_ids) | set(already_running_ids) | set(failed_ids)
    skipped_ids = list(requested_ids - acted_ids)

    return {
        "message": f"已恢复 {len(resumed_ids)} 个任务",
        "resumed": resumed_ids,
        "already_running": already_running_ids,
        "skipped": skipped_ids,
        "failed": failed_ids,
    }


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


@router.post(
    "/reply-collection/batch-update",
    response_model=BatchUpdateReplyCollectionResponse,
    summary="批量切换任务采评模式",
    description=(
        "批量把历史帖子采集任务切换为“采集评论”或“不采集评论”。\n\n"
        "- 当前支持 `platform=x / weibo` 且 `task_kind=search` 的任务\n"
        "- 仅 `done / stopped / failed` 状态允许切换，避免影响运行中的任务\n"
        "- 切换后会更新任务配置；后续继续 / 复爬时会按新配置执行\n"
        "- 对 X 来说，开启评论采集时会统一按二级评论模式执行"
    ),
)
async def batch_update_reply_collection(
    req: BatchUpdateReplyCollectionRequest,
) -> BatchUpdateReplyCollectionResponse:
    result = task_reply_collection_service.batch_update_reply_collection(req.task_ids, req.mode)
    return BatchUpdateReplyCollectionResponse(**result)


@router.post(
    "/merge/preview",
    response_model=MergePreviewResponse,
    summary="合并任务预览",
    description=(
        "预览合并操作的结果。按关键词+平台分组，显示每组的任务数、推文总量和去重后的估计数量。\n\n"
        "- 仅已完成/已停止/已失败的任务参与合并\n"
        "- 运行中/排队中/已暂停的任务不参与\n"
        "- 每组至少需要 2 个同关键词任务才能合并"
    ),
)
async def merge_preview(req: MergePreviewRequest) -> MergePreviewResponse:
    """合并预览：返回分组和去重统计"""
    result = merge_service.preview_merge(req.task_ids)
    return MergePreviewResponse(**result)


@router.post(
    "/merge",
    response_model=MergeResponse,
    summary="合并任务",
    description=(
        "执行任务合并操作（不可逆）。\n\n"
        "- 同关键词+平台的任务将合并为一个\n"
        "- 保留最早创建的任务作为目标任务\n"
        "- 推文数据按 ID 去重，保留信息更完整的版本\n"
        "- 被吸收的任务将被删除\n"
        "- 仅已完成/已停止/已失败的任务参与合并"
    ),
)
async def merge_tasks(req: MergeRequest) -> MergeResponse:
    """执行合并操作：合并同关键词任务、去重推文、删除源任务"""
    result = merge_service.execute_merge(req.task_ids)

    if not result["merged_groups"]:
        return MergeResponse(
            message="没有可合并的任务组——需要至少 2 个相同关键词的非活跃任务",
            **result,
        )

    total_groups = len(result["merged_groups"])
    total_deleted = result["total_deleted_tasks"]
    return MergeResponse(
        message=f"已合并 {total_groups} 组任务，删除了 {total_deleted} 个源任务",
        **result,
    )
