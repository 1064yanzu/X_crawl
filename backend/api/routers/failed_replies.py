"""
失败评论记录路由

GET  /api/v1/failed-replies/{task_id}         查询任务的失败记录
POST /api/v1/failed-replies/{task_id}/retry    重试失败帖子的评论抓取
GET  /api/v1/failed-replies/{task_id}/export   导出失败记录为 CSV
"""
import io
import csv
import threading
import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.services import failed_replies_db, task_manager
from crawler.browser import ensure_browser_alive

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/failed-replies", tags=["失败评论记录"])


@router.get(
    "/{task_id}",
    summary="查询失败的评论记录",
    description="返回指定任务中评论爬取失败或不全的帖子列表，含预期/实际数量、失败原因、状态。",
)
async def list_failed_replies(task_id: str) -> dict:
    task = task_manager.get_task_summary(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    records = failed_replies_db.list_failed_replies(task_id)
    stats = failed_replies_db.count_failed_replies(task_id)
    return {
        "task_id": task_id,
        "records": records,
        "stats": stats,
    }


@router.post(
    "/{task_id}/retry",
    summary="重试失败帖子的评论抓取",
    description=(
        "对指定任务中所有 pending 状态的失败记录重新爬取评论。\n\n"
        "重试成功后将回复合并到任务数据中，并将记录状态更新为 resolved。"
    ),
)
async def retry_failed_replies(task_id: str) -> dict:
    task = task_manager.get_task_full(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    records = failed_replies_db.list_failed_replies(task_id)
    pending = [r for r in records if r["status"] == "pending"]
    if not pending:
        return {"message": "没有需要重试的失败记录", "retried": 0, "resolved": 0}

    # 在后台线程中执行重试，避免阻塞请求
    thread = threading.Thread(
        target=_retry_worker,
        args=(task_id, pending),
        daemon=True,
        name=f"retry-{task_id[:8]}",
    )
    thread.start()

    return {
        "message": f"已开始重试 {len(pending)} 条失败记录",
        "retried": len(pending),
    }


def _retry_worker(task_id: str, pending_records: list[dict]) -> None:
    """后台线程：逐条重试失败的评论抓取"""
    from crawler.reply_fetcher import fetch_replies

    ensure_browser_alive()

    resolved = 0
    task = task_manager.get_task_full(task_id)
    tweets = task.get("tweets", []) if task else []
    # 建立 tweet_id → tweet 索引
    tweet_index = {t.get("id", ""): t for t in tweets}

    for rec in pending_records:
        tweet_id = rec["tweet_id"]
        screen_name = rec.get("screen_name", "")
        expected = rec.get("expected_count", 0)

        if not tweet_id or not screen_name:
            continue

        # 更新状态为 retrying
        failed_replies_db.update_failed_reply_status(task_id, tweet_id, "retrying")

        try:
            logger.info(f"[重试] 开始重新抓取 tweet_id={tweet_id} 的评论...")
            replies, failure_info = fetch_replies(
                tweet_id=tweet_id,
                screen_name=screen_name,
                reply_limit=0,  # 不限制
                task_id=task_id,
                expected_count=expected,
            )

            if failure_info and len(replies) <= rec.get("fetched_count", 0):
                # 重试后仍然失败且数量没有增加
                failed_replies_db.update_failed_reply_status(
                    task_id, tweet_id, "pending", len(replies)
                )
                logger.warning(f"[重试] tweet_id={tweet_id} 仍然失败: {failure_info.get('error_reason', '')}")
            else:
                # 成功了（或比之前多了很多）→ 合并回任务数据
                if tweet_id in tweet_index:
                    tweet_index[tweet_id]["replies"] = replies
                failed_replies_db.update_failed_reply_status(
                    task_id, tweet_id, "resolved", len(replies)
                )
                resolved += 1
                logger.info(f"[重试] tweet_id={tweet_id} 成功, 获取 {len(replies)} 条评论")

        except Exception as e:
            logger.error(f"[重试] tweet_id={tweet_id} 异常: {e}", exc_info=True)
            failed_replies_db.update_failed_reply_status(
                task_id, tweet_id, "pending"
            )

    # 将更新后的推文数据持久化
    if resolved > 0 and task:
        updated_tweets = list(tweet_index.values())
        task_manager.update_task_result(
            task_id=task_id,
            tweets=updated_tweets,
            resumed=task.get("resumed", False),
            replies_fetched=sum(len(t.get("replies", [])) for t in updated_tweets),
        )

    logger.info(f"[重试] 完成: task_id={task_id}, 重试 {len(pending_records)} 条, 成功 {resolved} 条")


@router.get(
    "/{task_id}/export",
    summary="导出失败记录为 CSV",
    description="将失败的评论抓取记录导出为 CSV 文件。",
)
async def export_failed_replies(task_id: str):
    task = task_manager.get_task_summary(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    records = failed_replies_db.list_failed_replies(task_id)
    if not records:
        raise HTTPException(status_code=204, detail="该任务没有失败记录")

    buf = io.StringIO()
    headers = ["推文ID", "作者", "预期评论数", "实际抓取数", "失败原因", "状态", "记录时间", "重试时间"]
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for r in records:
        writer.writerow([
            r.get("tweet_id", ""),
            r.get("screen_name", ""),
            r.get("expected_count", 0),
            r.get("fetched_count", 0),
            r.get("error_reason", ""),
            r.get("status", ""),
            r.get("created_at", ""),
            r.get("retried_at", ""),
        ])

    data = "\ufeff".encode("utf-8") + buf.getvalue().encode("utf-8")
    keyword = task.get("keyword", "export")
    filename = f"failed_replies_{keyword[:30]}_{task_id[:8]}.csv"

    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
