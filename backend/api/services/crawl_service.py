"""
爬虫服务层（调度器驱动）。
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from api.services import task_manager, task_queue_manager
from api.services.failed_replies_db import record_failed_replies_batch
from api.services.task_scheduler import scheduler
from crawler.browser import ensure_browser_alive, reset_browser
from crawler.crawl_signals import ChallengeSignal, LoginRequiredPause, StopSignal
from crawler.account_dispatcher import get_dispatcher
from crawler.cookie_manager import load_cookies, save_cookies
from crawler.comment_backfill_runner import run_comment_backfill_task
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
        account_id=task.get("assigned_account_id"),
        keyword=task["keyword"],
        max_count=task["max_count"],
        product=task["product"],
        resume=resume,
        fetch_replies=task.get("fetch_replies", False),
        max_replies_per_tweet=task.get("max_replies_per_tweet", 20),
        reply_depth=task.get("reply_depth", 2),
        crawl_strategy=task.get("crawl_strategy", "bfs"),
        force_new_browser=force_new_browser,
        platform=task.get("platform", "x"),
        start_date=task.get("start_date"),
        end_date=task.get("end_date"),
        task_kind=task.get("task_kind", "search"),
        source_file_name=task.get("source_file_name"),
        source_task_id=task.get("source_task_id"),
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
    platform = task.get("platform", "x")
    enqueued = scheduler.enqueue(task_id, payload, platform=platform)
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
    platform: str = "x",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    task_kind: str = "search",
    source_file_name: Optional[str] = None,
    source_task_id: Optional[str] = None,
    account_id: Optional[str] = None,
) -> None:
    final_status = "failed"
    task_manager.update_task_status(task_id, "running")
    task_manager.update_task_phase(task_id, "任务开始执行，正在初始化浏览器...")
    telemetry.record_event(task_id, "crawler_started", status="running", phase="任务开始执行，正在初始化浏览器...")
    start_task_metrics(task_id)

    logger.info(
        f"任务开始: task_id={task_id}, keyword='{keyword}', "
        f"strategy={crawl_strategy}, fetch_replies={fetch_replies}, "
        f"resume={resume}, task_kind={task_kind}"
    )

    # ── 浏览器池模式：并发数>1 时按 slot 分配浏览器实例 ──────────────────
    # 同一个 slot 内不同平台（X/微博）的任务共享同一个浏览器实例
    from crawler.browser_pool import get_browser_pool, is_pool_mode_enabled
    _pool_mode = is_pool_mode_enabled()
    _browser_instance = None
    _slot_id: int | None = None

    if _pool_mode:
        try:
            pool_obj = get_browser_pool()
            _browser_instance, _slot_id = pool_obj.acquire(task_id, platform=platform)
        except Exception as e:
            logger.warning(f"[BrowserPool] 获取实例失败，回退到共享模式: {e}")
            _pool_mode = False
            _browser_instance = None
            _slot_id = None

    if not _pool_mode:
        if force_new_browser:
            reset_browser()
        ensure_browser_alive()

    # 如果指定了账号，注入其 Cookie
    if account_id:
        _inject_account_cookies(task_id, account_id)

    try:
        if task_kind == "comment_backfill":
            task_manager.update_task_phase(task_id, "已读取导入文件，开始补采评论...")
            result = run_comment_backfill_task(
                task_id=task_id,
                platform=platform,
                max_replies_per_tweet=max_replies_per_tweet,
                reply_depth=reply_depth,
            )
            runtime_metrics = get_metrics(task_id)
            quality_state = "partial" if result.failed_records else "complete"
            task_manager.update_task_phase(
                task_id,
                f"评论补采完成，累计处理 {result.progress.get('processed_posts', 0)} 条帖子，"
                f"评论 {result.replies_fetched} 条",
            )
            task_manager.update_comment_backfill_progress(task_id, result.progress)
            task_manager.update_task_result(
                task_id=task_id,
                tweets=result.tweets,
                resumed=resume,
                replies_fetched=result.replies_fetched,
                quality_state=quality_state,
                runtime_metrics=runtime_metrics,
            )
            if result.failed_records:
                _persist_failed_records(task_id, result.failed_records)
            telemetry.record_event(
                task_id,
                "comment_backfill_finished",
                status="done",
                phase="评论补采完成",
                delta_tweets=len(result.tweets),
                delta_replies=result.replies_fetched,
                meta={
                    "failed_posts": result.progress.get("failed_posts", 0),
                    "source_file_name": source_file_name,
                    "source_task_id": source_task_id,
                },
            )
            logger.info(
                "评论补采完成: task_id=%s, 平台=%s, 帖子=%s, 评论=%s, 失败=%s",
                task_id,
                platform,
                len(result.tweets),
                result.replies_fetched,
                result.progress.get("failed_posts", 0),
            )
            final_status = "done"
        elif platform == "weibo":
            result = _run_weibo_task(
                task_id=task_id,
                keyword=keyword,
                max_count=max_count,
                task_id_param=task_id,
                resume=resume,
                start_date=start_date,
                end_date=end_date,
                fetch_replies=fetch_replies,
                browser_instance=_browser_instance,
                slot_id=_slot_id,
            )
            tweets = result.posts
            replies_fetched = sum(
                int((tweet.get("comment_stats") or {}).get("fetched_total_count", 0))
                for tweet in tweets
            )
            task_manager.update_task_phase(
                task_id,
                f"微博任务执行完成，累计 {len(tweets)} 条微博，评论 {replies_fetched} 条"
            )
            task_manager.update_task_result(
                task_id=task_id,
                tweets=tweets,
                resumed=result.resumed,
                replies_fetched=replies_fetched,
                quality_state="complete",
                runtime_metrics=get_metrics(task_id),
            )
            telemetry.record_event(
                task_id, "crawler_finished", status="done",
                phase="微博任务执行完成",
                delta_tweets=len(tweets),
                delta_replies=replies_fetched,
            )
            logger.info(
                "微博任务完成: task_id=%s, 微博=%s, 评论=%s",
                task_id,
                len(tweets),
                replies_fetched,
            )
            final_status = "done"
        else:
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
                browser_instance=_browser_instance,
                slot_id=_slot_id,
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
            final_status = "done"
    except LoginRequiredPause as e:
        final_status = "paused"
        phase = str(e) or "检测到 X 登录态失效，请在浏览器完成登录后点击继续任务"
        task_manager.update_task_risk_paused(
            task_id,
            e.risk_state,
            phase,
            runtime_metrics=get_metrics(task_id),
        )
        telemetry.record_event(
            task_id,
            "crawler_login_paused",
            status="paused",
            phase=phase,
            risk_state=e.risk_state,
            meta={
                "reason": e.reason,
                "session_mode": e.session_mode,
                "effective_user_data_path": e.effective_user_data_path,
            },
        )
        logger.warning(
            f"任务进入登录暂停: task_id={task_id}, reason={e.reason}, "
            f"session_mode={e.session_mode}, profile={e.effective_user_data_path}"
        )
    except ChallengeSignal as e:
        final_status = "paused"
        if e.risk_state == "login_required":
            phase = str(e) or "检测到 X 登录态失效，请在浏览器完成登录后点击继续任务"
        elif e.risk_state == "search_blocked":
            phase = str(e) or "检测到 X 搜索接口异常（疑似账号风控），请更换账号或稍后重试"
        else:
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
        task_data = task_manager.get_task_full(task_id) or {}
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
        final_status = "stopped"
    except Exception as e:
        error_msg = str(e)
        # 先尝试保存已采集的数据（即使任务出错，已抓到的推文不应丢失）
        task_data = task_manager.get_task_full(task_id) or {}
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
        final_status = "failed"
    finally:
        # 归还浏览器实例到池中
        if _pool_mode and _browser_instance is not None:
            try:
                from crawler.browser_pool import get_browser_pool
                get_browser_pool().release(task_id)
            except Exception as e:
                logger.warning(f"[BrowserPool] 归还实例失败: {e}")
        task_manager.clear_thread(task_id)
        scheduler.mark_done(task_id)
        if final_status in ("done", "failed", "stopped"):
            task_queue_manager.notify_task_terminal(task_id, final_status)
        clear_metrics(task_id)


def _run_weibo_task(
    task_id: str,
    keyword: str,
    max_count: int,
    task_id_param: str,
    resume: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    fetch_replies: bool = False,
    browser_instance=None,
    slot_id: int | None = None,
):
    """微博爬虫任务入口（延迟导入，避免启动时加载 bs4）"""
    from crawler.weibo.searcher import search as weibo_search

    task_manager.update_task_phase(task_id, "正在初始化微博搜索...")
    return weibo_search(
        keyword=keyword,
        max_count=max_count,
        task_id=task_id_param,
        resume=resume,
        fetch_comments=fetch_replies,
        start_date=start_date,
        end_date=end_date,
        browser_instance=browser_instance,
        slot_id=slot_id,
    )


def _persist_failed_records(task_id: str, failed_records: list[dict]) -> None:
    try:
        for rec in failed_records:
            rec.setdefault("task_id", task_id)
        record_failed_replies_batch(failed_records)
        logger.info(f"已记录 {len(failed_records)} 条失败评论抓取: task_id={task_id}")
    except Exception as e:
        logger.error(f"记录失败评论失败: task_id={task_id}, error={e}", exc_info=True)


# ─── 账号注入与管理 ────────────────────────────────────────────────────────

def _inject_account_cookies(task_id: str, account_id: str) -> None:
    """
    为任务注入指定账号的 Cookie。

    直接将账号 Cookie 注入到浏览器 tab，不写入全局 Cookie 文件，
    避免并发任务之间互相覆盖 Cookie。
    """
    from crawler.account_pool import get_pool
    from crawler.auth import inject_account_cookies, ensure_login_with_pool_detailed

    pool = get_pool()
    account = pool.get_account(account_id)

    if not account:
        logger.warning(f"账号 {account_id} 不存在，跳过注入")
        return

    logger.info(f"为任务 {task_id[:8]} 注入账号 {account.alias} 的 Cookie...")

    try:
        from crawler.browser import get_new_tab
        tab = get_new_tab()

        # 直接将账号 Cookie 注入 tab，不经过全局文件
        injected = inject_account_cookies(tab, account)

        if injected > 0:
            logger.info(f"账号 {account.alias} 已注入 {injected} 条 Cookie")
            pool.mark_account_used(account_id)
        else:
            logger.warning(f"账号 {account.alias} 无 Cookie 可注入")
            pool.mark_account_invalid(account_id)

    except Exception as e:
        logger.error(f"注入账号 Cookie 失败: {e}", exc_info=True)
        pool.mark_account_invalid(account_id)


def _handle_task_account_lifecycle(task_id: str) -> None:
    """
    处理任务的账号生命周期：
    1. 任务开始时分配账号
    2. 任务结束时释放账号
    """
    dispatcher = get_dispatcher()

    # 尝试为任务分配账号
    account = dispatcher.assign_account(task_id)
    if account:
        task_manager.bind_account(task_id, account.account_id, account.alias)
        logger.info(f"为任务 {task_id[:8]} 分配账号 {account.alias}")
    else:
        logger.debug(f"暂无可用账号分配给任务 {task_id[:8]}")


def _release_task_account(task_id: str) -> None:
    """
    释放任务占用的账号。
    """
    dispatcher = get_dispatcher()
    if dispatcher.release_account(task_id):
        task_manager.release_account(task_id)
        logger.info(f"已释放任务 {task_id[:8]} 的账号")
