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
from crawler.comment_backfill_runner import run_comment_backfill_task, run_comment_backfill_group_task
from crawler import telemetry
from crawler.runtime_metrics import clear_metrics, get_metrics, start_task_metrics
from crawler.x_searcher import search
from config import settings

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
        time_split_mode=task.get("time_split_mode", "inherit"),
        time_split_window_days=task.get("time_split_window_days"),
        time_split_max_segments=task.get("time_split_max_segments"),
        task_kind=task.get("task_kind", "search"),
        source_file_name=task.get("source_file_name"),
        source_task_id=task.get("source_task_id"),
        source_task_ids=list(task.get("source_task_ids") or []),
        is_recrawl=bool(task.get("is_recrawl", False)),
        exclude_tweet_ids=task.get("exclude_tweet_ids") or [],
        youtube_params=task.get("youtube") if isinstance(task.get("youtube"), dict) else None,
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
    task_kind = task.get("task_kind", "search")
    # 任务组诊断：确保 source_task_ids 在调度链中不丢失
    if task_kind == "comment_backfill_group":
        logger.info(
            "任务组调度: task_id=%s, task.source_task_ids=%r, payload.source_task_ids=%r",
            task_id[:8], task.get("source_task_ids"), payload.get("source_task_ids"),
        )
    cbp = task.get("comment_backfill_progress") or {}
    total_expected_replies = int(cbp.get("total_expected_replies") or 0)
    enqueued = scheduler.enqueue(
        task_id, payload,
        platform=platform,
        task_kind=task_kind,
        result_count=int(task.get("result_count") or 0),
        total_expected_replies=total_expected_replies,
    )
    if enqueued:
        task_manager.update_task_status(task_id, "pending")
        task_manager.update_task_phase(task_id, "任务已进入调度队列，等待执行...")
        telemetry.record_event(
            task_id,
            "scheduler_enqueued",
            status="pending",
            phase="任务已进入调度队列，等待执行...",
        )
    else:
        logger.info(f"任务重复入队已忽略: task_id={task_id}")


def run_search_task(
    task_id: str,
    keyword: str,
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
    time_split_mode: str = "inherit",
    time_split_window_days: Optional[int] = None,
    time_split_max_segments: Optional[int] = None,
    task_kind: str = "search",
    source_file_name: Optional[str] = None,
    source_task_id: Optional[str] = None,
    source_task_ids: Optional[list[str]] = None,
    is_recrawl: bool = False,
    account_id: Optional[str] = None,
    exclude_tweet_ids: Optional[list[str]] = None,
    youtube_params: Optional[dict] = None,
) -> None:
    final_status = "failed"
    task_manager.update_task_status(task_id, "running")
    task_manager.update_task_phase(task_id, "任务开始执行，正在初始化浏览器...")
    telemetry.record_event(
        task_id,
        "crawler_started",
        status="running",
        phase="任务开始执行，正在初始化浏览器...",
    )
    start_task_metrics(task_id)

    logger.info(
        f"任务开始: task_id={task_id}, keyword='{keyword}', "
        f"strategy={crawl_strategy}, fetch_replies={fetch_replies}, "
        f"resume={resume}, task_kind={task_kind}, is_recrawl={is_recrawl}"
    )

    effective_exclude_tweet_ids = list(exclude_tweet_ids or [])
    if is_recrawl and not effective_exclude_tweet_ids:
        effective_exclude_tweet_ids = task_manager.ensure_task_exclude_tweet_ids(
            task_id
        )

    reserved_account_id = account_id

    # ── 浏览器池模式：并发数>1 时按 slot 分配浏览器实例 ──────────────────
    # 每个任务获得独立的搜索浏览器实例
    # 如果需要抓取回复/评论，还会获得额外的独立浏览器实例
    # 搜索和回复使用不同 Chrome 进程，确保 CDP 命令不串行化
    from crawler.browser_pool import get_browser_pool, is_pool_mode_enabled

    _pool_mode = is_pool_mode_enabled()
    _browser_instance = None
    _reply_browser_instance = None  # L1回复/评论专用独立浏览器实例
    _nested_browser_instance = None  # L2二级评论专用独立浏览器实例（完全解耦）
    _slot_id: int | None = None
    _multi_account_mode = False  # 任务组并发模式标记
    _worker_resources: list | None = None  # 并发模式的资源列表

    try:
        # ── 判断是否为并发任务组模式 ──
        _group_concurrency = 1
        if task_kind == "comment_backfill_group":
            task_full = task_manager.get_task_full(task_id)
            _group_concurrency = int((task_full or {}).get("concurrency") or 1)

        # YouTube 走 HTTP API，不需要浏览器/账号池，跳过所有相关初始化。
        _skip_browser_and_account = platform == "youtube"

        # 账号分配（可能抛出 LoginRequiredPause，必须在 try 内确保 finally 清理）
        if (
            not _skip_browser_and_account
            and platform == "x"
            and bool(getattr(settings, "account_pool_enabled", True))
        ):
            dispatcher = get_dispatcher()

            # ── 并发任务组：分配多个账号 ──
            if _group_concurrency > 1:
                from crawler.parallel_backfill_coordinator import WorkerResource

                max_concurrency = min(
                    _group_concurrency,
                    int(getattr(settings, "comment_backfill_group_max_concurrency", 3)),
                )
                multi_accounts = dispatcher.assign_multiple_accounts(task_id, max_concurrency)
                if not multi_accounts:
                    # 回退到单账号模式
                    logger.warning(
                        "任务组 %s 无法分配多账号，回退单账号模式", task_id[:8],
                    )
                    _group_concurrency = 1
                else:
                    _multi_account_mode = True
                    # 首个账号绑定到任务显示
                    reserved_account_id = multi_accounts[0].account_id
                    aliases = [a.alias for a in multi_accounts]
                    task_manager.bind_account(
                        task_id, multi_accounts[0].account_id,
                        f"{multi_accounts[0].alias} 等 {len(multi_accounts)} 个",
                    )
                    logger.info(
                        "任务组 %s 并发模式: 分配 %d 个账号 %s",
                        task_id[:8], len(multi_accounts), aliases,
                    )

            # ── 单账号模式（默认路径 / 并发回退） ──
            if not _multi_account_mode:
                reserved_account = None
                if account_id:
                    reserved_account = dispatcher.reserve_account(task_id, account_id)
                    if reserved_account is None:
                        logger.warning(
                            "任务 %s 预留已绑定账号失败，尝试重新分配可用账号",
                            task_id[:8],
                        )
                if reserved_account is None:
                    reserved_account = dispatcher.assign_account(task_id)
                if reserved_account is not None:
                    reserved_account_id = reserved_account.account_id
                    task_manager.bind_account(
                        task_id, reserved_account.account_id, reserved_account.alias
                    )
                else:
                    from crawler.account_pool import get_pool

                    if get_pool().get_active_account_count() > 0:
                        raise LoginRequiredPause(
                            f"X 账号池已启用，但当前所有账号均被占用，任务 {task_id[:8]} 已暂停等待账号释放",
                            reason="no_account_available",
                            session_mode="pool",
                            effective_user_data_path=None,
                        )
                    reserved_account_id = None
                    logger.warning("任务 %s 当前没有可用 X 账号，将回退默认登录态", task_id[:8])

        if _pool_mode and not _skip_browser_and_account:
            pool_obj = get_browser_pool()
            _browser_instance, _slot_id = pool_obj.acquire(task_id, platform=platform)

            # ── 并发任务组：为每个账号获取独立的 L1 + L2 浏览器 ──
            if _multi_account_mode and multi_accounts:
                from crawler.parallel_backfill_coordinator import WorkerResource

                _worker_resources = []
                # 并发模式下只分配 1 个共享 nested 浏览器（减少 Chrome 进程总数）
                shared_nested = pool_obj.acquire_aux(task_id, purpose="nested_shared") if reply_depth > 1 else None
                if shared_nested is not None:
                    # 用首个账号注入 Cookie（nested browser 用于二级评论，账号影响较小）
                    _inject_account_cookies(task_id, multi_accounts[0].account_id, browser_instance=shared_nested)
                for i, acc in enumerate(multi_accounts):
                    l1 = pool_obj.acquire_aux(task_id, purpose=f"reply_w{i}")
                    # 注入该账号的 Cookie 到 L1 浏览器
                    _inject_account_cookies(task_id, acc.account_id, browser_instance=l1)
                    _worker_resources.append(WorkerResource(
                        account_id=acc.account_id,
                        account_alias=acc.alias,
                        reply_browser=l1,
                        nested_browser=shared_nested,  # 共享
                    ))
                n_browsers = len(multi_accounts) + (1 if shared_nested else 0)
                logger.info(
                    "任务组 %s 浏览器资源就绪: %d 个 L1 + %s 共享 L2，共 %d 个 Chrome 进程",
                    task_id[:8], len(multi_accounts),
                    "1 个" if shared_nested else "无",
                    n_browsers,
                )
            else:
                # ── 普通单账号浏览器获取 ──
                needs_reply_browser = bool(fetch_replies or task_kind in ("comment_backfill", "comment_backfill_group"))
                if needs_reply_browser:
                    _reply_browser_instance = pool_obj.acquire_aux(
                        task_id,
                        purpose="reply" if platform == "x" else "comment",
                    )
                needs_nested_browser = bool(
                    task_kind == "comment_backfill_group"
                    or (needs_reply_browser and platform == "x" and int(reply_depth) > 1)
                )
                if needs_nested_browser:
                    _nested_browser_instance = pool_obj.acquire_aux(
                        task_id,
                        purpose="nested_reply",
                    )

        if not _pool_mode and not _skip_browser_and_account:
            if force_new_browser:
                reset_browser()
            ensure_browser_alive()

        # 单账号模式下注入 Cookie
        if reserved_account_id and not _multi_account_mode and not _skip_browser_and_account:
            _inject_account_cookies(
                task_id, reserved_account_id, browser_instance=_browser_instance
            )
            if _reply_browser_instance is not None:
                _inject_account_cookies(
                    task_id, reserved_account_id, browser_instance=_reply_browser_instance
                )
            if _nested_browser_instance is not None:
                _inject_account_cookies(
                    task_id, reserved_account_id, browser_instance=_nested_browser_instance
                )

        if task_kind == "comment_backfill_group":
            task_manager.update_task_phase(task_id, "正在初始化评论补采任务组...")
            result = run_comment_backfill_group_task(
                task_id=task_id,
                max_replies_per_tweet=max_replies_per_tweet,
                reply_depth=reply_depth,
                browser_instance=_browser_instance,
                reply_browser_instance=_reply_browser_instance,
                nested_browser_instance=_nested_browser_instance,
                source_task_ids=source_task_ids,
                worker_resources=_worker_resources,
            )
            runtime_metrics = get_metrics(task_id)
            quality_state = "partial" if result.failed_records else "complete"
            task_manager.update_task_phase(
                task_id,
                f"任务组补采完成，共处理 {result.progress.get('processed_posts', 0)} 条帖子，"
                f"累计评论 {result.replies_fetched} 条",
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
                "comment_backfill_group_finished",
                status="done",
                phase="任务组补采完成",
                delta_tweets=len(result.tweets),
                delta_replies=result.replies_fetched,
                meta={
                    "failed_posts": result.progress.get("failed_posts", 0),
                    "source_task_ids": source_task_ids or [],
                },
            )
            logger.info(
                "评论补采任务组完成: task_id=%s, 帖子=%s, 评论=%s, 失败=%s",
                task_id,
                len(result.tweets),
                result.replies_fetched,
                result.progress.get("failed_posts", 0),
            )
            final_status = "done"
        elif task_kind == "comment_backfill":
            task_manager.update_task_phase(task_id, "已读取导入文件，开始补采评论...")
            effective_backfill_browser = (
                _reply_browser_instance
                if platform == "weibo" and _reply_browser_instance is not None
                else _browser_instance
            )
            result = run_comment_backfill_task(
                task_id=task_id,
                platform=platform,
                max_replies_per_tweet=max_replies_per_tweet,
                reply_depth=reply_depth,
                browser_instance=effective_backfill_browser,
                reply_browser_instance=_reply_browser_instance,
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
        elif platform == "youtube":
            final_status = _run_youtube_task(
                task_id=task_id,
                keyword=keyword,
                resume=resume,
                fetch_replies=fetch_replies,
                max_replies_per_tweet=max_replies_per_tweet,
                reply_depth=reply_depth,
                start_date=start_date,
                end_date=end_date,
                youtube_params=youtube_params,
                exclude_ids=effective_exclude_tweet_ids,
            )
        elif platform == "weibo":
            result = _run_weibo_task(
                task_id=task_id,
                keyword=keyword,
                task_id_param=task_id,
                resume=resume,
                start_date=start_date,
                end_date=end_date,
                time_split_mode=time_split_mode,
                time_split_window_days=time_split_window_days,
                time_split_max_segments=time_split_max_segments,
                fetch_replies=fetch_replies,
                browser_instance=_browser_instance,
                comment_browser_instance=_reply_browser_instance,
                slot_id=_slot_id,
                exclude_tweet_ids=effective_exclude_tweet_ids,
            )
            tweets = result.posts
            replies_fetched = sum(
                int((tweet.get("comment_stats") or {}).get("fetched_total_count", 0))
                for tweet in tweets
            )
            task_manager.update_task_phase(
                task_id,
                f"微博任务执行完成，累计 {len(tweets)} 条微博，评论 {replies_fetched} 条",
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
                task_id,
                "crawler_finished",
                status="done",
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
            # ── 时间分段任务 recrawl 时不传 seed_tweets，交由 x_searcher 内部时间分段逻辑处理 ──
            # 检查方式：查看任务的 segment_progress 是否启用
            task_summary = task_manager.get_task_summary(task_id) or {}
            segment_progress = task_summary.get("segment_progress", {})
            is_time_split_task = segment_progress.get("enabled", False) and segment_progress.get("total_segments", 0) > 0
            
            seed_tweets = (
                task_manager._get_task_result_snapshot(task_id, load=True)
                if is_recrawl and effective_exclude_tweet_ids and not is_time_split_task
                else []
            )
            result = search(
                keyword=keyword,
                product=product,
                task_id=task_id,
                resume=resume,
                fetch_replies=fetch_replies,
                max_replies_per_tweet=max_replies_per_tweet,
                reply_depth=reply_depth,
                crawl_strategy=crawl_strategy,
                browser_instance=_browser_instance,
                reply_browser_instance=_reply_browser_instance,
                slot_id=_slot_id,
                exclude_ids=set(effective_exclude_tweet_ids)
                if effective_exclude_tweet_ids
                else None,
                recrawl_mode=is_recrawl,
                seed_tweets=seed_tweets,
                time_split_mode=time_split_mode,
                time_split_window_days=time_split_window_days,
                time_split_max_segments=time_split_max_segments,
            )
            runtime_metrics = get_metrics(task_id)
            quality_state = "partial" if result.failed_replies else "complete"

            # ── 判断时间分段是否全部完成，再决定任务最终状态 ────────────────
            segment_complete = True
            completed = 0
            total = 0
            task_summary = task_manager.get_task_summary(task_id) or {}
            segment_progress = task_summary.get("segment_progress", {})
            if segment_progress.get("enabled") and segment_progress.get(
                "total_segments"
            ):
                completed = segment_progress.get("completed_segments", 0)
                total = segment_progress.get("total_segments", 0)
                segment_complete = completed >= total

            status_val = "done" if segment_complete else "stopped"
            phase_val = (
                "任务执行完成"
                if segment_complete
                else f"时间分片未完成（{completed}/{total}），已暂停等待继续"
            )

            if segment_complete:
                task_manager.update_task_result(
                    task_id=task_id,
                    tweets=result.tweets,
                    resumed=result.resumed,
                    replies_fetched=result.replies_fetched,
                    quality_state=quality_state,
                    runtime_metrics=runtime_metrics,
                )
            else:
                task_manager.update_task_phase(task_id, phase_val)
                task_manager.update_task_stopped(
                    task_id,
                    result.tweets,
                    runtime_metrics=runtime_metrics,
                )

            if result.failed_replies:
                _persist_failed_records(task_id, result.failed_replies)

            telemetry.record_event(
                task_id,
                "crawler_finished",
                status=status_val,
                phase=phase_val,
                delta_tweets=len(result.tweets),
                delta_replies=result.replies_fetched,
                meta={"failed_replies": len(result.failed_replies)},
            )
            logger.info(
                f"任务完成: task_id={task_id}, 推文={len(result.tweets)}, "
                f"回复={result.replies_fetched}, 失败评论={len(result.failed_replies)}, "
                f"分片完成={segment_complete}"
            )
            final_status = status_val
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
            phase = (
                str(e) or "检测到 X 搜索接口异常（疑似账号风控），请更换账号或稍后重试"
            )
        else:
            phase = (
                f"检测到风控挑战（{e.risk_state}），请在浏览器完成验证后点击继续任务"
            )
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
        logger.warning(
            f"任务进入风控暂停: task_id={task_id}, risk={e.risk_state}, reason={e}"
        )
    except StopSignal as e:
        task_data = task_manager.get_task_full(task_id) or {}
        tweets_so_far = task_data.get("tweets", [])
        task_manager.update_task_stopped(
            task_id, tweets_so_far, runtime_metrics=get_metrics(task_id)
        )
        telemetry.record_event(
            task_id,
            "crawler_stopped",
            status="stopped",
            phase="任务已收到停止信号并安全退出",
            meta={"saved_tweets": len(tweets_so_far)},
        )
        logger.info(
            f"任务主动终止: task_id={task_id}, 已保存 {len(tweets_so_far)} 条数据, reason={e}"
        )
        final_status = "stopped"
    except Exception as e:
        error_msg = str(e)
        # 先尝试保存已采集的数据（即使任务出错，已抓到的推文不应丢失）
        task_data = task_manager.get_task_full(task_id) or {}
        tweets_so_far = task_data.get("tweets", [])
        if tweets_so_far:
            task_manager.update_task_stopped(
                task_id, tweets_so_far, runtime_metrics=get_metrics(task_id)
            )
            task_manager.update_task_error(task_id, error_msg)
            telemetry.record_event(
                task_id,
                "crawler_error_partial",
                status="failed",
                phase="任务异常退出（已保留部分数据）",
                meta={"error": error_msg[:240], "saved_tweets": len(tweets_so_far)},
            )
            logger.info(
                f"任务异常终止但已保存 {len(tweets_so_far)} 条数据: task_id={task_id}"
            )
        else:
            task_manager.update_task_error(
                task_id, error_msg, runtime_metrics=get_metrics(task_id)
            )
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
        if platform == "x" and final_status in ("done", "failed", "stopped", "paused"):
            if _multi_account_mode:
                # 释放并发模式下分配的所有账号
                try:
                    released = get_dispatcher().release_multiple_accounts(task_id)
                    logger.info("已释放任务组 %s 的 %d 个并发账号", task_id[:8], released)
                except Exception as e:
                    logger.warning("释放任务组多账号失败: %s", e)
            _release_task_account(task_id)
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
        # 统一清理所有模块级 per-task 资源（page_health / circuit_breaker / rate_tracker 等）
        try:
            from crawler.browser_lifecycle import cleanup_task_resources
            cleanup_task_resources(task_id)
        except Exception:
            pass


def _run_weibo_task(
    task_id: str,
    keyword: str,
    task_id_param: str,
    resume: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    time_split_mode: str = "inherit",
    time_split_window_days: Optional[int] = None,
    time_split_max_segments: Optional[int] = None,
    fetch_replies: bool = False,
    browser_instance=None,
    comment_browser_instance=None,
    slot_id: int | None = None,
    exclude_tweet_ids: Optional[list[str]] = None,
):
    """微博爬虫任务入口（延迟导入，避免启动时加载 bs4）"""
    from crawler.weibo.searcher import search as weibo_search

    task_manager.update_task_phase(task_id, "正在初始化微博搜索...")
    seed_tweets = (
        task_manager._get_task_result_snapshot(task_id, load=True)
        if exclude_tweet_ids
        else []
    )
    return weibo_search(
        keyword=keyword,
        task_id=task_id_param,
        resume=resume,
        fetch_comments=fetch_replies,
        start_date=start_date,
        end_date=end_date,
        time_split_mode=time_split_mode,
        time_split_window_days=time_split_window_days,
        time_split_max_segments=time_split_max_segments,
        browser_instance=browser_instance,
        comment_browser_instance=comment_browser_instance,
        slot_id=slot_id,
        exclude_ids=set(exclude_tweet_ids) if exclude_tweet_ids else None,
        seed_posts=seed_tweets,
    )


def _run_youtube_task(
    *,
    task_id: str,
    keyword: str,
    resume: bool = True,
    fetch_replies: bool = False,
    max_replies_per_tweet: int = 0,
    reply_depth: int = 1,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    youtube_params: Optional[dict] = None,
    exclude_ids: Optional[list[str]] = None,
) -> str:
    """
    执行 YouTube 任务。
    返回最终状态字符串（done / paused / stopped / failed），由外层 finally 负责清理。
    """
    from crawler.crawl_signals import StopSignal
    from crawler.utils import check_signal
    from crawler.youtube import api_client, searcher

    yt_params = dict(youtube_params or {})
    source = str(yt_params.get("source") or "keyword").strip().lower()
    if source not in ("keyword", "channel", "video_urls"):
        source = "keyword"

    max_videos = int(yt_params.get("max_videos") or 50)
    order = str(yt_params.get("order") or "relevance")
    region_code = yt_params.get("region_code") or None
    relevance_language = yt_params.get("relevance_language") or None
    video_duration = str(yt_params.get("video_duration") or "any")
    video_definition = str(yt_params.get("video_definition") or "any")
    type_filter = str(yt_params.get("type") or "video")

    exclude_id_set: Optional[set[str]] = set(exclude_ids) if exclude_ids else None

    def _signal_checker(_task_id: Optional[str]) -> None:
        check_signal(_task_id)

    def _on_progress(phase: str, page: Optional[int], videos: list[dict]) -> None:
        task_manager.update_task_phase(task_id, phase)
        if videos:
            task_manager.update_preview_tweets(
                task_id,
                current_page=page or 0,
                tweets_for_preview=videos,
            )

    task_manager.update_task_phase(task_id, "[YouTube] 任务已启动，正在检查 API Key 池...")

    try:
        if source == "channel":
            channel_input = str(yt_params.get("channel_input") or "").strip()
            if not channel_input:
                raise RuntimeError("YouTube 频道采集任务缺少 channel_input 参数")
            result = searcher.crawl_channel(
                channel_input=channel_input,
                task_id=task_id,
                resume=resume,
                max_videos=max_videos,
                fetch_replies=fetch_replies,
                reply_depth=reply_depth,
                max_replies_per_video=max_replies_per_tweet,
                signal_checker=_signal_checker,
                on_progress=_on_progress,
                exclude_ids=exclude_id_set,
            )
        elif source == "video_urls":
            video_urls_raw = yt_params.get("video_urls") or []
            if isinstance(video_urls_raw, str):
                video_urls_list: list[str] = [video_urls_raw]
            else:
                video_urls_list = [str(item) for item in video_urls_raw if str(item).strip()]
            if not video_urls_list:
                raise RuntimeError("YouTube 视频链接批量采集任务缺少 video_urls 参数")
            result = searcher.crawl_by_video_ids(
                video_urls=video_urls_list,
                task_id=task_id,
                resume=resume,
                max_videos=max_videos,
                fetch_replies=fetch_replies,
                reply_depth=reply_depth,
                max_replies_per_video=max_replies_per_tweet,
                signal_checker=_signal_checker,
                on_progress=_on_progress,
                exclude_ids=exclude_id_set,
            )
        else:
            result = searcher.search(
                keyword=keyword,
                task_id=task_id,
                resume=resume,
                max_videos=max_videos,
                fetch_replies=fetch_replies,
                reply_depth=reply_depth,
                max_replies_per_video=max_replies_per_tweet,
                order=order,
                region_code=region_code,
                relevance_language=relevance_language,
                video_duration=video_duration,
                video_definition=video_definition,
                type_filter=type_filter,
                published_after=start_date,
                published_before=end_date,
                signal_checker=_signal_checker,
                on_progress=_on_progress,
                exclude_ids=exclude_id_set,
            )
    except api_client.YouTubeKeyMissing as exc:
        phase = str(exc) or "[YouTube] 未配置任何可用 API Key，任务已暂停等待补齐"
        task_manager.update_task_risk_paused(
            task_id,
            "login_required",
            phase,
            runtime_metrics=get_metrics(task_id),
        )
        telemetry.record_event(
            task_id,
            "youtube_key_missing",
            status="paused",
            phase=phase,
            risk_state="login_required",
        )
        return "paused"
    except api_client.YouTubeQuotaExhausted as exc:
        reset_at = getattr(exc, "reset_at", None)
        phase = (
            f"[YouTube] API 配额已耗尽，将于 {reset_at} 重置，任务已暂停"
            if reset_at
            else "[YouTube] API 配额已耗尽，任务已暂停等待手动恢复"
        )
        task_manager.update_task_risk_paused(
            task_id,
            "rate_limited",
            phase,
            runtime_metrics=get_metrics(task_id),
        )
        telemetry.record_event(
            task_id,
            "youtube_quota_exhausted",
            status="paused",
            phase=phase,
            risk_state="rate_limited",
            meta={"reset_at": reset_at},
        )
        return "paused"
    except StopSignal:
        raise
    except Exception as exc:
        logger.error("YouTube 任务异常 task_id=%s: %s", task_id, exc, exc_info=True)
        raise

    videos = result.videos
    replies_fetched = result.replies_fetched
    runtime_metrics = get_metrics(task_id)
    quality_state = "partial" if result.quota_exhausted else "complete"
    phase_text = (
        f"[YouTube] 任务完成，共抓取 {len(videos)} 个视频"
        + (f"，评论 {replies_fetched} 条" if replies_fetched else "")
    )
    task_manager.update_task_phase(task_id, phase_text)
    task_manager.update_task_result(
        task_id=task_id,
        tweets=videos,
        resumed=result.resumed,
        replies_fetched=replies_fetched,
        quality_state=quality_state,
        runtime_metrics=runtime_metrics,
    )
    telemetry.record_event(
        task_id,
        "crawler_finished",
        status="done",
        phase=phase_text,
        delta_tweets=len(videos),
        delta_replies=replies_fetched,
    )
    logger.info(
        "YouTube 任务完成: task_id=%s videos=%s replies=%s",
        task_id,
        len(videos),
        replies_fetched,
    )
    return "done"


def _persist_failed_records(task_id: str, failed_records: list[dict]) -> None:
    try:
        for rec in failed_records:
            rec.setdefault("task_id", task_id)
        record_failed_replies_batch(failed_records)
        logger.info(f"已记录 {len(failed_records)} 条失败评论抓取: task_id={task_id}")
    except Exception as e:
        logger.error(f"记录失败评论失败: task_id={task_id}, error={e}", exc_info=True)


# ─── 账号注入与管理 ────────────────────────────────────────────────────────


def _inject_account_cookies(
    task_id: str, account_id: str, browser_instance=None
) -> None:
    """
    为任务的浏览器实例注入指定账号的 Cookie。

    通过 browser_instance.set_cookies() 设置 cookie，后续所有新 tab 自动继承。
    """
    from crawler.account_pool import get_pool

    pool = get_pool()
    account = pool.get_account(account_id)

    if not account:
        logger.warning(f"账号 {account_id} 不存在，跳过注入")
        return

    if not browser_instance:
        logger.warning(f"未提供 browser_instance，无法注入 cookie")
        return

    if not account.cookies:
        logger.warning(f"账号 {account.alias} 无 Cookie 可注入")
        return

    logger.info(
        f"为任务 {task_id[:8]} 的浏览器实例注入账号 {account.alias} 的 Cookie..."
    )

    try:
        # 设置到浏览器实例，后续所有新 tab 自动继承
        browser_instance.set_cookies(
            account.cookies,
            account_id=account.account_id,
            account_alias=account.alias,
        )
        logger.info(
            f"账号 {account.alias} 已设置 {len(account.cookies)} 条 Cookie 到浏览器实例"
        )
        pool.mark_account_used(account_id)
    except Exception as e:
        logger.error(f"设置账号 Cookie 到浏览器实例失败: {e}", exc_info=True)


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
