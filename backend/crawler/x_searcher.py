"""
X 搜索爬虫核心模块（v4 - 人性化渐进滚动 + 统一 DFS 策略）

变更（v4）：
- 移除 BFS/DFS 策略区分，统一为 DFS 模式（搜到一批立即抓评论）
- 搜索翻页改为人性化渐进式滚动（模拟人类浏览行为）
- 每页检查任务控制信号（pause/stop），可随时暂停或终止
- Referer 头由浏览器自动管理（根据抓包分析无需手动设置）
"""
import logging
from typing import Literal, Optional
from urllib.parse import quote

from crawler.browser import get_new_tab
from crawler.human_scroll import human_like_scroll, simulate_reading, idle_scroll
from crawler.auth import ensure_login
from crawler.parser import parse_search_response
from crawler.checkpoint import save_checkpoint, load_checkpoint, delete_checkpoint
from crawler.checkpoint_buffer import (
    stage_reply_checkpoint,
    flush_reply_checkpoint,
    clear_reply_checkpoint,
)
from crawler.response_saver import save_raw_response
from crawler.page_health import navigate_with_retry
from crawler.page_state import detect_page_state, PageState
from crawler.packet_guard import wait_for_target_packet, is_search_timeline_body
from crawler.recovery_policy import RecoveryPolicy, soft_recover_for_packet, backoff_seconds, sleep_with_jitter
from crawler.crawl_signals import StopSignal, ChallengeSignal, RiskState
from crawler.utils import jittered_sleep, check_signal, merge_remaining
from crawler.runtime_metrics import bump_metric
from crawler import telemetry
import api.services.task_manager as _task_mgr
from config import settings

logger = logging.getLogger(__name__)

SEARCH_TIMELINE_PATTERN = "SearchTimeline"
SEARCH_URL_TEMPLATE = "https://x.com/search?q={query}&src=typed_query"

ProductType = Literal["Top", "Latest", "Photos", "Videos"]
CrawlStrategy = Literal["bfs", "dfs"]  # 保留类型定义兼容旧调用，实际统一走 DFS

_TAB_MAP: dict[str, str] = {
    "Top": "",
    "Latest": "&f=live",
    "Photos": "&f=image",
    "Videos": "&f=video",
}

class SearchResult:
    """搜索结果容器"""

    def __init__(
        self,
        tweets: list[dict],
        total_fetched: int,
        keyword: str,
        resumed: bool = False,
        replies_fetched: int = 0,
        stopped: bool = False,
        failed_replies: list[dict] | None = None,
    ):
        self.tweets = tweets
        self.total_fetched = total_fetched
        self.keyword = keyword
        self.resumed = resumed
        self.replies_fetched = replies_fetched
        self.stopped = stopped
        self.failed_replies = failed_replies or []


def _to_risk_state(state: PageState) -> RiskState:
    if state == PageState.RATE_LIMITED:
        return "rate_limited"
    if state == PageState.LOGIN_REQUIRED:
        return "login_required"
    return "challenge"


def _wait_search_packet_with_recovery(
    *,
    tab,
    timeout: float,
    page_num: int,
    task_id: Optional[str],
    policy: RecoveryPolicy,
):
    """等待搜索包：软重试失败后进入硬刷新恢复。"""
    challenge_hits = 0

    for soft_attempt in range(policy.packet_soft_retries + 1):
        packet, ignored = wait_for_target_packet(
            tab,
            timeout=timeout,
            accept_body=is_search_timeline_body,
        )
        if packet:
            if ignored:
                logger.debug(f"第 {page_num} 页过滤无关包 {ignored} 个")
            return packet
        bump_metric(task_id, "search_packet_timeouts")

        state, reason = detect_page_state(tab)
        if state in {PageState.CHALLENGE, PageState.RATE_LIMITED, PageState.LOGIN_REQUIRED}:
            challenge_hits += 1
            bump_metric(task_id, "risk_hits")
            if challenge_hits > policy.challenge_retry_times:
                raise ChallengeSignal(
                    f"第 {page_num} 页检测到 {state.value} 且重试耗尽：{reason}",
                    risk_state=_to_risk_state(state),
                )
            logger.warning(
                f"第 {page_num} 页检测到风险状态 state={state.value}，"
                f"将在冷却后重试（{challenge_hits}/{policy.challenge_retry_times}）"
            )
            sleep_with_jitter(policy.challenge_cooldown, jitter_ratio=0.1, minimum=0.8)

        if soft_attempt < policy.packet_soft_retries:
            logger.info(f"第 {page_num} 页软恢复重试 {soft_attempt + 1}/{policy.packet_soft_retries}")
            bump_metric(task_id, "soft_retries")
            soft_recover_for_packet(tab, soft_attempt)

    for hard_attempt in range(policy.refresh_max_retries):
        bump_metric(task_id, "hard_refreshes")
        wait = backoff_seconds(hard_attempt, base=2.0, cap=35.0)
        logger.warning(
            f"第 {page_num} 页进入硬恢复：第 {hard_attempt + 1}/{policy.refresh_max_retries} 次刷新，"
            f"退避 {wait:.1f}s"
        )
        sleep_with_jitter(wait, jitter_ratio=0.2, minimum=0.6)
        tab.listen.stop()
        ok = navigate_with_retry(
            tab,
            tab.url,
            max_retries=1,
            base_wait=2.5,
            post_load_wait=settings.crawler_initial_wait,
            challenge_retry_times=policy.challenge_retry_times,
            challenge_cooldown=policy.challenge_cooldown,
            raise_on_risk=True,
            task_id=task_id,
        )
        tab.listen.start(SEARCH_TIMELINE_PATTERN)
        if not ok:
            continue
        packet, _ = wait_for_target_packet(
            tab,
            timeout=timeout,
            accept_body=is_search_timeline_body,
        )
        if packet:
            return packet

    return None




def search(
    keyword: str,
    max_count: int = 0,
    product: ProductType = "Top",
    timeout: Optional[float] = None,
    task_id: Optional[str] = None,
    resume: bool = True,
    fetch_replies: bool = False,
    max_replies_per_tweet: int = 20,
    reply_depth: int = 2,
    crawl_strategy: CrawlStrategy = "dfs",  # 保留参数兼容旧调用，统一走 DFS
) -> SearchResult:
    """
    搜索 X 推文（含断点续爬 + 可选回复抓取 + 可暂停/可终止）

    Args:
        keyword:               搜索关键词
        max_count:             最多获取的推文数量（0 表示不限制）
        product:               搜索类型
        timeout:               等待每个数据包的超时（秒）
        task_id:               任务 ID（用于检查点文件命名和原始响应存储）
        resume:                是否尝试从已有检查点继续（True = 断点续爬）
        fetch_replies:         是否抓取每条推文的回复
        max_replies_per_tweet: 每条推文最多抓取的回复数量
        crawl_strategy:        已弃用，统一使用 DFS 策略（保留参数兼容旧调用）

    Returns:
        SearchResult 对象
    """
    if timeout is None:
        timeout = settings.crawler_timeout
    policy = RecoveryPolicy.from_settings(settings)

    # DFS 增量保存 checkpoint 时闭包需要的搜索参数
    _search_keyword = keyword
    _search_product = product

    # ── 1. 尝试加载检查点 ───────────────────────────────────────────
    all_tweets: list[dict] = []
    seen_ids: set[str] = set()
    start_cursor: Optional[str] = None
    page_fetched: int = 0
    resumed = False
    _all_failed_records: list[dict] = []  # 收集所有失败的回复记录
    _last_bottom_cursor: Optional[str] = None  # 追踪最后有效 cursor，用于兜底保存

    if resume and task_id:
        ckpt = load_checkpoint(task_id)
        if ckpt and ckpt.get("keyword") == keyword and ckpt.get("product") == product:
            all_tweets = ckpt.get("tweets", [])
            seen_ids = {t["id"] for t in all_tweets if t.get("id")}
            start_cursor = ckpt.get("next_cursor")
            page_fetched = ckpt.get("page_fetched", 0)
            resumed = True
            logger.info(
                f"从断点恢复：task_id={task_id}，"
                f"已有 {len(all_tweets)} 条，cursor={'有' if start_cursor else '无'}"
            )

            # ── 无 cursor 但无限模式：保留旧推文去重，从头搜索拾取新推文 ──
            if not start_cursor and not max_count:
                logger.info(
                    f"断点恢复（无cursor/无限模式）：保留 {len(all_tweets)} 条旧推文用于去重，"
                    f"开始新搜索以拾取新推文"
                )
                page_fetched = 0  # 重置页码
                # 不 return，继续走搜索流程

            elif (max_count and len(all_tweets) >= max_count) or not start_cursor:
                # 断点恢复时若搜索已完成，直接进入回复抓取阶段
                _resume_failed: list[dict] = []
                if fetch_replies:
                    # 检查是否还有未抓取回复的推文（跳过已有 replies 的推文由下层处理）
                    tweets_without_replies = [t for t in all_tweets if not t.get("replies")]
                    if tweets_without_replies:
                        logger.info(
                            f"断点恢复：{len(all_tweets)} 条推文中 {len(tweets_without_replies)} 条"
                            f"尚未抓取回复，继续抓取..."
                        )
                        all_tweets, _resume_failed = _fetch_replies_for_tweets(
                            all_tweets, max_replies_per_tweet, task_id, timeout, crawl_strategy,
                            reply_depth=reply_depth,
                        )
                    else:
                        logger.info("断点恢复：所有推文已有回复数据，跳过回复抓取")
                return SearchResult(
                    tweets=all_tweets[:max_count] if max_count else all_tweets,
                    total_fetched=len(all_tweets[:max_count] if max_count else all_tweets),
                    keyword=keyword,
                    resumed=resumed,
                    replies_fetched=_count_replies(all_tweets),
                    failed_replies=_resume_failed,
                )

    # ── 2. 启动浏览器标签页 ─────────────────────────────────────────
    tab = get_new_tab()
    try:
        if not ensure_login(tab):
            raise RuntimeError(
                "未检测到 X 登录状态。"
                "请先在浏览器中登录 X 账号，"
                "程序会自动检测已登录的 Chrome 用户数据目录。"
            )

        search_url = _build_search_url(keyword, product)
        logger.info(
            f"开始搜索: keyword='{keyword}', product={product}, "
            f"max_count={max_count}, strategy=unified_dfs, "
            f"fetch_replies={fetch_replies}, 从断点={resumed}"
        )
        telemetry.record_event(
            task_id,
            "search_started",
            status="running",
            phase="搜索任务已开始",
            meta={"keyword": keyword, "product": product, "resumed": resumed},
        )

        # ── 3. 开启监听 ─────────────────────────────────────────────
        tab.listen.start(SEARCH_TIMELINE_PATTERN)

        # ── 4. 访问搜索页面（含错误页自动刷新）───────────────────────────
        ok = navigate_with_retry(
            tab,
            search_url,
            max_retries=policy.refresh_max_retries,
            base_wait=3.0,
            load_timeout=30.0,
            post_load_wait=settings.crawler_initial_wait,
            challenge_retry_times=policy.challenge_retry_times,
            challenge_cooldown=policy.challenge_cooldown,
            raise_on_risk=True,
            task_id=task_id,
        )
        if not ok:
            raise RuntimeError(f"搜索页面反复出现错误，无法加载: {search_url}")

        page_num = page_fetched + 1

        while not max_count or len(all_tweets) < max_count:
            # 每页开始前检查控制信号
            check_signal(task_id)

            logger.info(f"等待第 {page_num} 页数据包（timeout={timeout}s）...")
            if task_id:
                _task_mgr.update_task_phase(task_id, f"等待第 {page_num} 页数据包...")
                telemetry.record_event(
                    task_id,
                    "search_wait_packet",
                    status="running",
                    phase=f"等待第 {page_num} 页数据包...",
                    page=page_num,
                )
            packet = _wait_search_packet_with_recovery(
                tab=tab,
                timeout=timeout,
                page_num=page_num,
                task_id=task_id,
                policy=policy,
            )
            if not packet:
                logger.warning(f"第 {page_num} 页连续恢复后仍超时，停止爬取")
                telemetry.record_event(
                    task_id,
                    "search_packet_timeout_stop",
                    status="running",
                    phase=f"第 {page_num} 页连续恢复后仍超时，停止爬取",
                    page=page_num,
                )
                break

            try:
                body = packet.response.body
                if not isinstance(body, dict):
                    logger.debug(f"非 JSON 响应，跳过（url={packet.url[:80]}）")
                    continue

                # 保存原始搜索响应
                if task_id:
                    save_raw_response(task_id, page_num, body)

                tweets_page, bottom_cursor, _ = parse_search_response(body)
                if bottom_cursor:
                    _last_bottom_cursor = bottom_cursor  # 追踪最后有效 cursor

                # 去重
                new_tweets = [t for t in tweets_page if t.get("id") not in seen_ids]
                for t in new_tweets:
                    seen_ids.add(t.get("id", ""))

                # ── 模拟人类阅读：慢慢浏览本页推文 ────────────────────
                if new_tweets:
                    simulate_reading(tab, task_id=task_id, tweet_count=len(new_tweets))

                # ── 每批新推文立即抓取回复（统一 DFS 策略） ───────────
                if fetch_replies and new_tweets:
                    logger.info(f"立即抓取 {len(new_tweets)} 条新推文的回复...")

                    # 进入回复抓取前，先把已搜到的推文推入预览（仅更新预览，不覆盖 tweets）
                    # ★ 关键修复：不使用 update_task_progress 保存无回复的 tweets，
                    #   避免后续 _persist 调用用无回复版本覆盖数据库
                    if task_id:
                        _task_mgr.update_task_phase(
                            task_id,
                            f"第 {page_num} 页已解析 {len(new_tweets)} 条，正在抓取回复..."
                        )
                        # 更新预览推文 + 同步 tweets 到内存和 DB
                        _task_mgr.update_preview_tweets(
                            task_id, page_num, list(all_tweets) + new_tweets
                        )
                        # 保存 checkpoint：确保搜索到的推文在回复抓取阶段崩溃时不丢失
                        save_checkpoint(
                            task_id=task_id,
                            keyword=_search_keyword,
                            product=_search_product,
                            tweets_so_far=list(all_tweets) + new_tweets,
                            next_cursor=bottom_cursor,
                            page_fetched=page_num,
                        )

                    # 停止搜索监听，切换到回复抓取，完成后重新开启搜索监听
                    tab.listen.stop()

                    # 闭包引用 all_tweets，使回调能增量保存 checkpoint
                    _dfs_all_tweets_ref = all_tweets  # 引用当前 all_tweets
                    # ★ 使用共享可变列表追踪已完成回复的推文
                    #   fetch_replies_batch 对推文做 dict() 浅拷贝后才设置 replies，
                    #   原始列表中的推文不会被修改，不能直接过滤原始列表
                    _dfs_processed: list[dict] = []
                    # 建立索引加速查找
                    _dfs_tweet_index = {t.get("id", ""): t for t in new_tweets}

                    def _on_reply_progress(tweet_id: str, replies: list[dict]):
                        """每条推文回复抓取完成后更新进度，并按批次/时间窗刷新 checkpoint。"""
                        # 从原始推文中找到对应记录，合并 replies 后追加到已处理列表
                        orig = _dfs_tweet_index.get(tweet_id)
                        if orig is not None:
                            processed_tweet = dict(orig)
                            processed_tweet["replies"] = replies
                            _dfs_processed.append(processed_tweet)

                        if task_id:
                            _task_mgr.update_task_replies_progress(task_id, tweet_id, len(replies))
                            interim_tweets = list(_dfs_all_tweets_ref) + list(_dfs_processed)
                            flushed = stage_reply_checkpoint(
                                task_id=task_id,
                                keyword=_search_keyword,
                                product=_search_product,
                                tweets_so_far=interim_tweets,
                                next_cursor=bottom_cursor,
                                page_fetched=page_num,
                            )
                            if flushed:
                                _task_mgr.update_task_progress(task_id, page_num, interim_tweets)

                        # DFS 期间让搜索页保持微滚动（模拟人类偶尔回来看看）
                        try:
                            idle_scroll(tab, task_id=task_id)
                        except Exception:
                            pass

                    try:
                        new_tweets, _dfs_failed = _fetch_replies_for_tweets(
                            new_tweets, max_replies_per_tweet, task_id, timeout,
                            strategy="dfs",
                            progress_callback=_on_reply_progress,
                            reply_depth=reply_depth,
                        )
                        if task_id:
                            flush_reply_checkpoint(task_id)
                        _all_failed_records.extend(_dfs_failed)
                    except ChallengeSignal:
                        if task_id:
                            flush_reply_checkpoint(task_id)
                        raise
                    except StopSignal as e:
                        if task_id:
                            flush_reply_checkpoint(task_id)
                        # 即使被中断，也要合并已处理的部分结果（含已抓取的回复）
                        if e.partial_tweets:
                            all_tweets.extend(e.partial_tweets)
                        if task_id:
                            _task_mgr.update_task_progress(task_id, page_num, list(all_tweets))
                            save_checkpoint(
                                task_id=task_id,
                                keyword=_search_keyword,
                                product=_search_product,
                                tweets_so_far=list(all_tweets),
                                next_cursor=bottom_cursor,
                                page_fetched=page_num,
                            )
                        raise
                    finally:
                        tab.listen.start(SEARCH_TIMELINE_PATTERN)
                        if task_id:
                            clear_reply_checkpoint(task_id)

                all_tweets.extend(new_tweets)

                logger.info(
                    f"第 {page_num} 页：{len(tweets_page)} 条（新增 {len(new_tweets)} 条），"
                    f"累计 {len(all_tweets)} 条"
                )
                telemetry.record_event(
                    task_id,
                    "search_page_parsed",
                    status="running",
                    phase=f"第 {page_num} 页解析完成",
                    page=page_num,
                    delta_tweets=len(new_tweets),
                    meta={"page_total": len(tweets_page), "all_total": len(all_tweets)},
                )

                # 写检查点（每页立即保存）
                if task_id:
                    save_checkpoint(
                        task_id=task_id,
                        keyword=keyword,
                        product=product,
                        tweets_so_far=all_tweets,
                        next_cursor=bottom_cursor,
                        page_fetched=page_num,
                    )
                    _task_mgr.update_task_progress(task_id, page_num, list(all_tweets))
                    _task_mgr.update_task_phase(task_id, f"已完成第 {page_num} 页，共 {len(all_tweets)} 条")

                if not bottom_cursor:
                    logger.info("无更多数据（bottom_cursor 为空），停止")
                    break
                if max_count and len(all_tweets) >= max_count:
                    logger.info(f"已达目标 {max_count} 条，停止")
                    break

            except StopSignal:
                raise
            except ChallengeSignal:
                raise
            except Exception as e:
                logger.error(f"第 {page_num} 页解析失败: {e}", exc_info=True)
                break

            # 人性化渐进滚动翻页（模拟人类浏览行为）
            page_num += 1
            jittered_sleep(settings.crawler_page_interval, task_id=task_id)
            telemetry.record_event(
                task_id,
                "search_scroll_next_page",
                status="running",
                phase=f"准备进入第 {page_num} 页，执行滚动翻页",
                page=page_num,
            )
            human_like_scroll(tab, task_id=task_id)

    finally:
        if task_id:
            flush_reply_checkpoint(task_id)
            clear_reply_checkpoint(task_id)
        # ── 安全兜底：无论何种原因退出，都尝试保存已采集数据 ──
        if task_id and all_tweets:
            try:
                save_checkpoint(
                    task_id=task_id,
                    keyword=keyword,
                    product=product,
                    tweets_so_far=all_tweets,
                    next_cursor=_last_bottom_cursor,  # 使用最后有效 cursor，而非 None
                    page_fetched=page_num,
                )
                _task_mgr.update_task_progress(task_id, page_num, list(all_tweets))
                logger.info(
                    f"安全兜底保存: {len(all_tweets)} 条推文已持久化"
                    f"（cursor={'有' if _last_bottom_cursor else '无'}）"
                )
            except Exception as e:
                logger.error(f"安全兜底保存失败: {e}")
        try:
            tab.listen.stop()
            tab.close()
        except Exception:
            pass

    if max_count:
        all_tweets = all_tweets[:max_count]

    # ── BFS 分支已移除：统一使用 DFS，每批搜索结果中已即时处理评论 ──

    # 爬取完成，删除检查点（仅在有限模式且达到目标数量时删除）
    # 无限模式(max_count=0)保留 checkpoint，便于后续恢复继续爬取新推文
    if task_id and max_count and len(all_tweets) >= max_count:
        delete_checkpoint(task_id)

    result = SearchResult(
        tweets=all_tweets,
        total_fetched=len(all_tweets),
        keyword=keyword,
        resumed=resumed,
        replies_fetched=_count_replies(all_tweets),
        failed_replies=_all_failed_records,
    )
    logger.info(
        f"搜索完成：{result.total_fetched} 条推文，"
        f"回复 {result.replies_fetched} 条，"
        f"失败 {len(result.failed_replies)} 条，"
        f"resumed={resumed}"
    )
    telemetry.record_event(
        task_id,
        "search_finished",
        status="done",
        phase="搜索流程完成",
        delta_tweets=result.total_fetched,
        delta_replies=result.replies_fetched,
        meta={"failed_replies": len(result.failed_replies), "resumed": resumed},
    )
    return result


# ═══════════════════════════════════════════════════════════════════
#  回复抓取辅助
# ═══════════════════════════════════════════════════════════════════

def _fetch_replies_for_tweets(
    tweets: list[dict],
    max_replies_per_tweet: int,
    task_id: Optional[str],
    timeout: Optional[float],
    strategy: str,
    progress_callback=None,
    reply_depth: int = 2,
) -> tuple[list[dict], list[dict]]:
    """统一的回复抓取入口（BFS/DFS 共用），返回 (updated_tweets, failed_records)"""
    from crawler.reply_fetcher import fetch_replies_batch

    def on_progress(tweet_id: str, replies: list[dict]):
        if task_id:
            _task_mgr.update_task_replies_progress(task_id, tweet_id, len(replies))
        if progress_callback:
            progress_callback(tweet_id, replies)

    return fetch_replies_batch(
        tweets=tweets,
        max_replies_per_tweet=max_replies_per_tweet,
        task_id=task_id,
        timeout=timeout,
        progress_callback=on_progress,
        strategy=strategy,
        reply_depth=reply_depth,
    )


def _count_replies(tweets: list[dict]) -> int:
    """统计推文列表中回复总数"""
    return sum(len(tweet.get("replies", [])) for tweet in tweets)


# ═══════════════════════════════════════════════════════════════════
#  URL 构建
# ═══════════════════════════════════════════════════════════════════

def _build_search_url(keyword: str, product: ProductType) -> str:
    """构建搜索 URL"""
    return SEARCH_URL_TEMPLATE.format(query=quote(keyword)) + _TAB_MAP.get(product, "")
