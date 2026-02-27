"""
爬虫服务层（调度器驱动）。
"""
from __future__ import annotations

import logging
import threading

from api.services import task_manager
from api.services.failed_replies_db import record_failed_replies_batch
from api.services.task_scheduler import scheduler
from crawler.browser import ensure_browser_alive, reset_browser
from crawler.crawl_signals import ChallengeSignal, StopSignal
from crawler import telemetry
from crawler.runtime_metrics import clear_metrics, get_metrics, start_task_metrics
from crawler.x_searcher import search

logger = logging.getLogger(__name__)


def _spawn_worker(task_id: str, payload: dict) -> threading.Thread:
    thread = threading.Thread(
        target=run_search_task,
        kwargs=payload,
        daemon=True,
        name=f"crawler-{task_id[:8]}",
    )
    thread.start()
    task_manager.register_thread(task_id, thread)
    return thread


scheduler.register_executor(_spawn_worker)


def _build_worker_payload(
    task_id: str,
    task: dict,
    *,
    force_new_browser: bool,
    resume: bool,
) -> dict:
    return dict(
        task_id=task_id,
        keyword=task["keyword"],
        max_count=task["max_count"],
        product=task["product"],
        resume=resume,
        fetch_replies=task.get("fetch_replies", False),
        max_replies_per_tweet=task.get("max_replies_per_tweet", 20),
        reply_depth=task.get("reply_depth", 2),
        crawl_strategy=task.get("crawl_strategy", "bfs"),
        force_new_browser=force_new_browser,
    )


def start_crawler_thread(
    task_id: str,
    task: dict,
    force_new_browser: bool = False,
    resume: bool = True,
) -> None:
    payload = _build_worker_payload(
        task_id=task_id,
        task=task,
        force_new_browser=force_new_browser,
        resume=resume,
    )
    enqueued = scheduler.enqueue(task_id, payload)
    if enqueued:
        task_manager.update_task_status(task_id, "pending")
        task_manager.update_task_phase(task_id, "任务已进入调度队列，等待执行...")
        telemetry.record_event(task_id, "scheduler_enqueued", status="pending", phase="任务已进入调度队列，等待执行...")
    else:
        logger.info(f"任务重复入队已忽略: task_id={task_id}")


def run_search_task(
    task_id: str,
    keyword: str,
    max_count: int,
    product: str,
    resume: bool = True,
    fetch_replies: bool = False,
    max_replies_per_tweet: int = 20,
    reply_depth: int = 2,
    crawl_strategy: str = "bfs",
    force_new_browser: bool = False,
) -> None:
    task_manager.update_task_status(task_id, "running")
    task_manager.update_task_phase(task_id, "任务开始执行，正在初始化浏览器...")
    telemetry.record_event(task_id, "crawler_started", status="running", phase="任务开始执行，正在初始化浏览器...")
    start_task_metrics(task_id)

    logger.info(
        f"任务开始: task_id={task_id}, keyword='{keyword}', "
        f"strategy={crawl_strategy}, fetch_replies={fetch_replies}, resume={resume}"
    )

    if force_new_browser:
        reset_browser()
    ensure_browser_alive()

    try:
        result = search(
            keyword=keyword,
            max_count=max_count,
            product=product,
            task_id=task_id,
            resume=resume,
            fetch_replies=fetch_replies,
            max_replies_per_tweet=max_replies_per_tweet,
            reply_depth=reply_depth,
            crawl_strategy=crawl_strategy,
        )
        runtime_metrics = get_metrics(task_id)
        quality_state = "partial" if result.failed_replies else "complete"
        task_manager.update_task_result(
            task_id=task_id,
            tweets=result.tweets,
            resumed=result.resumed,
            replies_fetched=result.replies_fetched,
            quality_state=quality_state,
            runtime_metrics=runtime_metrics,
        )
        if result.failed_replies:
            _persist_failed_records(task_id, result.failed_replies)
        telemetry.record_event(
            task_id,
            "crawler_finished",
            status="done",
            phase="任务执行完成",
            delta_tweets=len(result.tweets),
            delta_replies=result.replies_fetched,
            meta={"failed_replies": len(result.failed_replies)},
        )
        logger.info(
            f"任务完成: task_id={task_id}, 推文={len(result.tweets)}, "
            f"回复={result.replies_fetched}, 失败评论={len(result.failed_replies)}"
        )
    except ChallengeSignal as e:
        phase = f"检测到风控挑战（{e.risk_state}），请在浏览器完成验证后点击继续任务"
        task_manager.update_task_risk_paused(
            task_id,
            e.risk_state,
            phase,
            runtime_metrics=get_metrics(task_id),
        )
        telemetry.record_event(
            task_id,
            "crawler_risk_paused",
            status="paused",
            phase=phase,
            risk_state=e.risk_state,
        )
        logger.warning(f"任务进入风控暂停: task_id={task_id}, risk={e.risk_state}, reason={e}")
    except StopSignal as e:
        task_data = task_manager.get_task(task_id) or {}
        tweets_so_far = task_data.get("tweets", [])
        task_manager.update_task_stopped(task_id, tweets_so_far, runtime_metrics=get_metrics(task_id))
        telemetry.record_event(
            task_id,
            "crawler_stopped",
            status="stopped",
            phase="任务已收到停止信号并安全退出",
            meta={"saved_tweets": len(tweets_so_far)},
        )
        logger.info(f"任务主动终止: task_id={task_id}, 已保存 {len(tweets_so_far)} 条数据, reason={e}")
    except Exception as e:
        error_msg = str(e)
        # 先尝试保存已采集的数据（即使任务出错，已抓到的推文不应丢失）
        task_data = task_manager.get_task(task_id) or {}
        tweets_so_far = task_data.get("tweets", [])
        if tweets_so_far:
            task_manager.update_task_stopped(task_id, tweets_so_far, runtime_metrics=get_metrics(task_id))
            task_manager.update_task_error(task_id, error_msg)
            telemetry.record_event(
                task_id,
                "crawler_error_partial",
                status="failed",
                phase="任务异常退出（已保留部分数据）",
                meta={"error": error_msg[:240], "saved_tweets": len(tweets_so_far)},
            )
            logger.info(f"任务异常终止但已保存 {len(tweets_so_far)} 条数据: task_id={task_id}")
        else:
            task_manager.update_task_error(task_id, error_msg, runtime_metrics=get_metrics(task_id))
            telemetry.record_event(
                task_id,
                "crawler_error",
                status="failed",
                phase="任务异常退出",
                meta={"error": error_msg[:240]},
            )
        logger.error(f"任务失败: task_id={task_id}, error={error_msg}", exc_info=True)
    finally:
        task_manager.clear_thread(task_id)
        scheduler.mark_done(task_id)
        clear_metrics(task_id)


def _persist_failed_records(task_id: str, failed_records: list[dict]) -> None:
    try:
        for rec in failed_records:
            rec.setdefault("task_id", task_id)
        record_failed_replies_batch(failed_records)
        logger.info(f"已记录 {len(failed_records)} 条失败评论抓取: task_id={task_id}")
    except Exception as e:
        logger.error(f"记录失败评论失败: task_id={task_id}, error={e}", exc_info=True)
