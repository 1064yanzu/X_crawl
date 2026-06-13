"""
X 搜索爬虫核心模块（v4 - 人性化渐进滚动 + 统一 DFS 策略）

变更（v4）：
- 移除 BFS/DFS 策略区分，统一为 DFS 模式（搜到一批立即抓评论）
- 搜索翻页改为人性化渐进式滚动（模拟人类浏览行为）
- 每页检查任务控制信号（pause/stop），可随时暂停或终止
- Referer 头由浏览器自动管理（根据抓包分析无需手动设置）
"""

import logging
import time
import random
from typing import Literal, Optional
from urllib.parse import quote

from crawler.browser import get_new_tab
from crawler.human_scroll import human_like_scroll, simulate_reading, idle_scroll
from crawler.auth import (
    ensure_login_detailed,
    ensure_login_with_pool,
    ensure_login_with_pool_detailed,
)
from crawler.cookie_manager import load_cookies
from crawler.parser import parse_search_response
from crawler.checkpoint import save_checkpoint, save_checkpoint_sync, load_checkpoint, delete_checkpoint
from crawler.checkpoint_buffer import (
    stage_reply_checkpoint,
    flush_reply_checkpoint,
    clear_reply_checkpoint,
)
from crawler.response_saver import save_raw_response
from crawler.page_health import navigate_with_retry
from crawler.page_state import detect_page_state, detect_no_results, detect_end_of_timeline, PageState
from crawler.packet_guard import (
    wait_for_target_packet,
    is_contentful_search_timeline_body,
    extract_packet_body_dict,
)
from crawler.recovery_policy import (
    RecoveryPolicy,
    soft_recover_for_packet,
    backoff_seconds,
    sleep_with_jitter,
    build_challenge_wait_plan,
    wait_for_challenge,
)
from crawler.crawl_signals import (
    StopSignal,
    ChallengeSignal,
    LoginRequiredPause,
    SplashTimeoutSignal,
    RiskState,
)
from crawler.utils import (
    jittered_sleep,
    check_signal,
    merge_remaining,
    interruptible_sleep,
)
from crawler.runtime_metrics import bump_metric
from crawler.rate_tracker import get_tracker, extract_rate_headers
from crawler.account_pool import get_pool, compute_dynamic_interval
from crawler import telemetry
from crawler.x_time_splitter import (
    TimeSplitSegment,
    build_query_with_window,
    build_time_split_plan,
    deserialize_segments,
    serialize_segments,
)
import api.services.task_manager as _task_mgr
from api.services.time_split_policy import resolve_task_time_split
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

# 搜索操作符前缀列表（用于判断是否需要预热导航）
_SEARCH_OPERATOR_PREFIXES = (
    "from:",
    "to:",
    "lang:",
    "since:",
    "until:",
    "min_faves:",
    "min_retweets:",
    "min_replies:",
    "filter:",
    "-",
    "@",
)


def _has_search_operators(keyword: str) -> bool:
    """检测关键词是否包含高级搜索操作符。"""
    tokens = keyword.split()
    for token in tokens:
        # 检查操作符前缀
        lower = token.lower()
        for prefix in _SEARCH_OPERATOR_PREFIXES:
            if lower.startswith(prefix):
                return True
        # 检查引号包裹的短语
        if token.startswith('"'):
            return True
        # 检查 OR 操作符
        if token == "OR":
            return True
        # 检查括号
        if token.startswith("(") or token.endswith(")"):
            return True
    return False


def _extract_base_keyword(keyword: str) -> str:
    """
    从包含搜索操作符的 keyword 中提取基础关键词（不含操作符的普通词）。
    用于预热导航：先搜索基础关键词，再跳转到完整高级搜索。

    例:
      'ChatGPT since:2022-01-01 until:2024-12-31' -> 'ChatGPT'
      'AI "machine learning" from:elonmusk'       -> 'AI'
      'from:elonmusk since:2024-01-01'              -> 'elonmusk'  (取 from 账号)
    """
    import re

    tokens = keyword.split()
    base_words: list[str] = []
    in_quote = False

    for token in tokens:
        # 跳过操作符 token
        lower = token.lower()
        is_operator = False
        for prefix in _SEARCH_OPERATOR_PREFIXES:
            if lower.startswith(prefix):
                is_operator = True
                break
        if token == "OR" or token.startswith("(") or token.endswith(")"):
            is_operator = True
        if token.startswith('"') or in_quote:
            # 引号短语也是操作符的一种
            if token.startswith('"'):
                in_quote = True
            if token.endswith('"'):
                in_quote = False
            is_operator = True

        if not is_operator:
            base_words.append(token)

    if base_words:
        return " ".join(base_words)


def _build_login_pause_message(result) -> str:
    profile_path = result.effective_user_data_path
    if result.session_mode == "crawler_profile":
        target = "当前爬虫专用浏览器会话"
        if profile_path:
            target += f"（profile: {profile_path}）"
    elif result.session_mode == "attached_browser":
        target = "当前已接管的 Chrome 会话"
    else:
        target = "当前浏览器会话"

    if result.reason == "challenge_required":
        action = f"请在{target}中完成安全验证后继续任务。"
    elif result.reason == "profile_missing_login":
        action = f"请先在{target}中登录 X 账号后继续任务。"
    else:
        action = f"已尝试注入持久化 Cookie，但未能恢复 {target} 的 X 登录态，请重新登录后继续任务。"

    return f"未检测到可用的 X 登录状态（reason={result.reason}）。{action}"


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


def _merge_tweets_by_id(*groups: list[dict]) -> list[dict]:
    merged: list[dict] = []
    index_by_id: dict[str, int] = {}
    for group in groups:
        for tweet in group or []:
            tweet_id = str(tweet.get("id", ""))
            if tweet_id and tweet_id in index_by_id:
                merged[index_by_id[tweet_id]] = tweet
                continue
            index_by_id[tweet_id] = len(merged)
            merged.append(tweet)
    return merged


def _build_segment_progress(
    *,
    enabled: bool,
    total_segments: int,
    completed_segments: int,
    current_segment_index: int,
    current_since: Optional[str],
    current_until: Optional[str],
) -> dict:
    return {
        "enabled": enabled,
        "total_segments": total_segments,
        "completed_segments": completed_segments,
        "current_segment_index": current_segment_index,
        "current_since": current_since,
        "current_until": current_until,
    }


def _search_with_time_splits(
    *,
    keyword: str,
    product: ProductType,
    timeout: Optional[float],
    task_id: Optional[str],
    resume: bool,
    fetch_replies: bool,
    max_replies_per_tweet: int,
    reply_depth: int,
    crawl_strategy: CrawlStrategy,
    checkpoint: Optional[dict] = None,
    browser_instance=None,
    reply_browser_instance=None,
    slot_id: Optional[int] = None,
    exclude_ids: Optional[set[str]] = None,
    recrawl_mode: bool = False,
    time_split_mode: str = "inherit",
    time_split_window_days: Optional[int] = None,
    time_split_max_segments: Optional[int] = None,
) -> SearchResult:
    shared_tab = (
        browser_instance.new_tab() if browser_instance is not None else get_new_tab()
    )
    try:
        if checkpoint and checkpoint.get("mode") == "time_split":
            base_query = str(checkpoint.get("base_query", "")).strip()
            segments = deserialize_segments(checkpoint.get("segments"))
            aggregated = checkpoint.get("aggregated_tweets", []) or []
            start_index = int(checkpoint.get("current_segment_index", 0))
        else:
            split_config = resolve_task_time_split(
                platform="x",
                keyword=keyword,
                start_date=None,
                end_date=None,
                time_split_mode=time_split_mode,
                time_split_window_days=time_split_window_days,
                time_split_max_segments=time_split_max_segments,
            )
            plan = build_time_split_plan(
                keyword,
                enabled=split_config.enabled,
                trigger_days=split_config.trigger_days,
                window_days=split_config.window_days,
                unlimited_window_days=split_config.window_days,
                max_segments=split_config.max_segments,
                force_window=split_config.force_window,
            )
            if not plan.enabled:
                raise RuntimeError("时间分割计划未启用，不能进入分段搜索")
            base_query = plan.base_query
            segments = plan.segments
            aggregated = []
            start_index = 0
            logger.info(f"固定 {plan.window_days} 天时间分割，共 {len(segments)} 段")

        seen_ids = {str(tweet.get("id", "")) for tweet in aggregated if tweet.get("id")}
        if exclude_ids:
            seen_ids |= exclude_ids
        total_segments = len(segments)
        seg_idx = -1

        for seg_idx in range(start_index, total_segments):
            segment = segments[seg_idx]
            progress = _build_segment_progress(
                enabled=True,
                total_segments=total_segments,
                completed_segments=seg_idx,
                current_segment_index=seg_idx + 1,
                current_since=segment.since,
                current_until=segment.until,
            )
            if task_id:
                _task_mgr.update_task_segment_progress(task_id, progress)
                _task_mgr.update_task_phase(
                    task_id,
                    f"正在执行时间分段 {seg_idx + 1}/{total_segments}: {segment.since} ~ {segment.until}",
                )

            segment_keyword = build_query_with_window(
                base_query, segment.since, segment.until
            )
            segment_result = search(
                keyword=segment_keyword,
                product=product,
                timeout=timeout,
                task_id=task_id,
                resume=resume and seg_idx == start_index,
                fetch_replies=False,  # 分片阶段只搜推文，全部分片完成后统一抓回复
                max_replies_per_tweet=max_replies_per_tweet,
                reply_depth=reply_depth,
                crawl_strategy=crawl_strategy,
                existing_tab=shared_tab,
                browser_instance=browser_instance,
                reply_browser_instance=reply_browser_instance,
                slot_id=slot_id,
                exclude_ids=seen_ids,  # 将已有推文 ID 传入每个 segment 用于去重
                _time_split_context={
                    "root_keyword": keyword,
                    "base_query": base_query,
                    "segments": serialize_segments(segments),
                    "current_segment_index": seg_idx,
                    "current_segment": {"since": segment.since, "until": segment.until},
                    "completed_segments": seg_idx,
                    "parent_tweets": aggregated,
                },
                time_split_mode=time_split_mode,
                time_split_window_days=time_split_window_days,
                time_split_max_segments=time_split_max_segments,
            )

            # ── 复爬段落级快跳：如果本段 0 条新增，说明已完全覆盖，跳到下段 ──
            if recrawl_mode and len(segment_result.tweets) == 0:
                logger.info(
                    f"复爬快跳：段 {seg_idx + 1}/{total_segments} "
                    f"({segment.since} ~ {segment.until}) 无新增，跳过"
                )
                if task_id:
                    _task_mgr.update_task_phase(
                        task_id,
                        f"复爬快跳段 {seg_idx + 1}/{total_segments}（无新增），下一段...",
                    )
            aggregated = _merge_tweets_by_id(aggregated, segment_result.tweets)
            seen_ids = {
                str(tweet.get("id", "")) for tweet in aggregated if tweet.get("id")
            }

            if task_id:
                progress = _build_segment_progress(
                    enabled=True,
                    total_segments=total_segments,
                    completed_segments=seg_idx + 1,
                    current_segment_index=min(seg_idx + 2, total_segments),
                    current_since=segments[seg_idx + 1].since
                    if seg_idx + 1 < total_segments
                    else None,
                    current_until=segments[seg_idx + 1].until
                    if seg_idx + 1 < total_segments
                    else None,
                )
                _task_mgr.update_task_segment_progress(task_id, progress)
                current_page = int(
                    (_task_mgr.get_task_summary(task_id) or {}).get("current_page", 0)
                )
                _task_mgr.update_task_progress(task_id, current_page, aggregated)

                save_checkpoint(
                    task_id=task_id,
                    keyword=segment_keyword,
                    product=product,
                    tweets_count=len(segment_result.tweets),  # 只传计数
                    next_cursor=None,
                    page_fetched=0,
                    extra={
                        "mode": "time_split",
                        "root_keyword": keyword,
                        "base_query": base_query,
                        "segments": serialize_segments(segments),
                        "current_segment_index": seg_idx + 1,
                        "aggregated_tweets": aggregated,
                        "segment_progress": progress,
                    },
                )

        final_tweets = aggregated
        actual_completed = seg_idx + 1 if seg_idx < total_segments else total_segments
        if task_id:
            actual_current = (
                actual_completed + 1
                if actual_completed < total_segments
                else total_segments
            )
            _task_mgr.update_task_segment_progress(
                task_id,
                _build_segment_progress(
                    enabled=True,
                    total_segments=total_segments,
                    completed_segments=actual_completed,
                    current_segment_index=actual_current,
                    current_since=None,
                    current_until=None,
                ),
            )

        # ── 所有分片搜完后，统一抓回复（不在每段内部等待）──────────────
        all_failed_replies: list[dict] = []
        if fetch_replies and final_tweets:
            if task_id:
                _task_mgr.update_task_phase(
                    task_id,
                    f"所有分段搜索完成（{len(final_tweets)} 条推文），开始统一抓取回复...",
                )
            logger.info(
                f"[TimeSplit] 全部 {total_segments} 段搜索完成，开始统一抓取 {len(final_tweets)} 条推文的回复"
            )
            final_tweets, all_failed_replies = _fetch_replies_for_tweets(
                final_tweets,
                max_replies_per_tweet,
                task_id,
                timeout,
                crawl_strategy,
                reply_depth=reply_depth,
                browser_instance=reply_browser_instance or browser_instance,
            )

        return SearchResult(
            tweets=final_tweets,
            total_fetched=len(final_tweets),
            keyword=keyword,
            resumed=bool(checkpoint),
            replies_fetched=_count_replies(final_tweets),
            failed_replies=all_failed_replies,
        )
    finally:
        try:
            shared_tab.listen.stop()
        except Exception:
            pass
        try:
            shared_tab.close()
        except Exception:
            pass


def _to_risk_state(state: PageState) -> RiskState:
    if state == PageState.RATE_LIMITED:
        return "rate_limited"
    if state == PageState.LOGIN_REQUIRED:
        return "login_required"
    return "challenge"


# 搜索无结果哨兵：当页面显示 "No results for ..." 时，
# _wait_search_packet_with_recovery 返回此对象而非 None（超时）或 packet
_NO_RESULTS_SENTINEL = object()

# 时间线到底哨兵：当页面内容很少且已滚动到底部，无更多内容可加载
_END_OF_TIMELINE_SENTINEL = object()


def _is_search_api_blocked(packet) -> tuple[bool, str]:
    try:
        url = getattr(packet, "url", "") or ""
        if SEARCH_TIMELINE_PATTERN.lower() not in url.lower():
            return False, ""
        response = getattr(packet, "response", None)
        status = getattr(response, "status", None)
        body = getattr(response, "body", None)
        body_len = len(body) if isinstance(body, (str, bytes, bytearray)) else 0
        if status in {401, 403, 404, 429} and body_len == 0:
            return True, f"SearchTimeline 接口返回 {status} 且响应体为空"
    except Exception:
        return False, ""
    return False, ""


def _wait_search_packet_with_recovery(
    *,
    tab,
    timeout: float,
    page_num: int,
    task_id: Optional[str],
    policy: RecoveryPolicy,
    fetched_count: int = 0,
):
    """等待搜索包：软重试失败后进入硬刷新恢复。
    
    Args:
        fetched_count: 当前已获取的推文数量。只有 > 0 时才会启用"到底"检测。
    """
    challenge_hits = 0
    search_api_blocked_hits = 0
    _no_results_detected = False  # 标记是否在等待期间检测到无结果

    def _inspect_packet(packet, body) -> None:
        nonlocal search_api_blocked_hits
        blocked, reason = _is_search_api_blocked(packet)
        if not blocked:
            return
        search_api_blocked_hits += 1
        bump_metric(task_id, "search_api_blocked_hits")
        logger.warning(
            f"第 {page_num} 页检测到搜索接口异常 {search_api_blocked_hits}/2：{reason}"
        )
        if search_api_blocked_hits >= 2:
            raise ChallengeSignal(
                f"{reason}，疑似当前账号被 X 搜索风控，请更换账号或稍后重试",
                risk_state="search_blocked",
            )

    def _check_no_results_early() -> bool:
        """在等待数据包期间快速检测页面是否显示无结果。

        注意：不在此处检测 detect_end_of_timeline，因为：
        1. 滚动后 at_bottom=True + X 虚拟滚动导致 DOM 中推文数少 → 极易误判
        2. API 响应可能尚未到达，loading indicator 也可能还没出现
        3. detect_end_of_timeline 仅在数据包等待超时后作为兜底检测（见下方）
        """
        nonlocal _no_results_detected
        if detect_no_results(tab):
            _no_results_detected = True
            logger.info(f"第 {page_num} 页在等待期间检测到搜索无结果页面")
            return True
        return False

    for soft_attempt in range(policy.packet_soft_retries + 1):
        _no_results_detected = False
        packet, ignored = wait_for_target_packet(
            tab,
            timeout=timeout,
            accept_body=is_contentful_search_timeline_body,
            on_packet=_inspect_packet,
            early_exit_check=_check_no_results_early,
        )
        
        # 如果在等待期间检测到无结果，立即返回哨兵
        if _no_results_detected:
            return _NO_RESULTS_SENTINEL
        
        if packet:
            if ignored:
                logger.debug(f"第 {page_num} 页过滤无关包 {ignored} 个")
            # ── 更新速率限制状态 ────────────────────────────────────
            _update_rate_tracker(packet, endpoint="search", task_id=task_id)
            return packet
        bump_metric(task_id, "search_packet_timeouts")
        # 断路器：搜索数据包超时也需记录
        from crawler.circuit_breaker import get_breaker
        get_breaker().record_error(task_id)

        # ── 快速检测搜索无结果页面 ─────────────────────────────────
        # X 的 "No results for ..." 页面可能不触发 SearchTimeline 请求，
        # 此时无需浪费时间做软重试/硬刷新，直接返回无结果哨兵
        if detect_no_results(tab):
            logger.info(f"第 {page_num} 页检测到搜索无结果页面，跳过重试")
            return _NO_RESULTS_SENTINEL
        
        # 只有已经拿到过数据才检测"到底"
        if fetched_count > 0 and detect_end_of_timeline(tab):
            logger.info(f"第 {page_num} 页检测到时间线已到底部，跳过重试（已获取 {fetched_count} 条）")
            return _END_OF_TIMELINE_SENTINEL

        state, reason = detect_page_state(tab)
        if state in {
            PageState.CHALLENGE,
            PageState.RATE_LIMITED,
            PageState.LOGIN_REQUIRED,
        }:
            challenge_hits += 1
            bump_metric(task_id, "risk_hits")
            if challenge_hits > policy.challenge_retry_times:
                raise ChallengeSignal(
                    f"第 {page_num} 页检测到 {state.value} 且重试耗尽：{reason}",
                    risk_state=_to_risk_state(state),
                )
            # 首次就提醒用户在浏览器中完成验证
            if challenge_hits == 1:
                from crawler.browser import promote_browser_for_manual_interaction

                promote_browser_for_manual_interaction(tab, reason=state.value)
            logger.warning(
                f"第 {page_num} 页检测到风险状态 state={state.value}，"
                f"等待用户完成验证（{challenge_hits}/{policy.challenge_retry_times}）"
            )
            wait_plan = build_challenge_wait_plan(
                tab,
                challenge_cooldown=policy.challenge_cooldown,
                cloudflare_wait_seconds=policy.cloudflare_wait_seconds,
            )
            if wait_plan.is_cloudflare:
                logger.info(
                    f"第 {page_num} 页命中 Cloudflare 验证，等待 {wait_plan.seconds:.0f}s 供用户手动完成"
                )
            wait_for_challenge(wait_plan, task_id=task_id)
            # 冷却后重新检测（不刷新，等用户手动完成验证）
            recheck_state, _ = detect_page_state(tab)
            if recheck_state == PageState.OK:
                logger.info(f"第 {page_num} 页用户已完成验证，页面恢复正常")
                continue  # 继续软重试流程

        if soft_attempt < policy.packet_soft_retries:
            logger.info(
                f"第 {page_num} 页软恢复重试 {soft_attempt + 1}/{policy.packet_soft_retries}"
            )
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
        try:
            tab.listen.stop()
        except Exception:
            pass
        tab.listen.start(SEARCH_TIMELINE_PATTERN, max_record=50)  # 限制缓存上限
        ok = navigate_with_retry(
            tab,
            tab.url,
            max_retries=1,
            base_wait=2.5,
            post_load_wait=0.5,
            challenge_retry_times=policy.challenge_retry_times,
            challenge_cooldown=policy.challenge_cooldown,
            raise_on_risk=True,
            task_id=task_id,
        )
        if not ok:
            continue
        packet, _ = wait_for_target_packet(
            tab,
            timeout=timeout,
            accept_body=is_contentful_search_timeline_body,
            on_packet=_inspect_packet,
        )
        if packet:
            _update_rate_tracker(packet, endpoint="search", task_id=task_id)
            return packet
        # 硬刷新后仍无包，检测是否为无结果页面
        if detect_no_results(tab):
            logger.info(f"第 {page_num} 页硬刷新后检测到搜索无结果页面，跳过后续重试")
            return _NO_RESULTS_SENTINEL

    return None


def _update_rate_tracker(packet, endpoint: str, task_id: Optional[str] = None) -> None:
    """从数据包提取速率限制头并更新 tracker，触发 maybe_wait_for_reset。"""
    result = extract_rate_headers(packet)
    if result:
        ep, remaining, limit, reset_ts = result
        get_tracker().update(ep, remaining, limit, reset_ts, task_id=task_id)
        get_tracker().maybe_wait_for_reset(ep, task_id=task_id)


def _try_rotate_account(
    tab,
    current_account,
    pool,
    reason: str,
    *,
    reply_browser_instance=None,
    task_id: Optional[str] = None,
) -> "AccountEntry | None":
    """
    尝试轮换到下一个账号。
    若无可用账号或只有一个账号则跳过。
    返回新账号（或 None 表示未轮换）。
    """
    if not pool or pool.total_count() <= 1:
        return None
    if task_id:
        bound_account_id, _ = _task_mgr.get_task_account(task_id)
        if bound_account_id:
            logger.info(
                f"任务 {task_id[:8]} 已绑定固定账号，跳过运行中换号（reason={reason}）"
            )
            return None
    current_id = current_account.account_id if current_account else None
    next_acc = pool.pick_next_account(current_id)
    if not next_acc or next_acc.account_id == current_id:
        return None
    logger.info(
        f"账号轮换（{reason}）: "
        f"{current_account.alias if current_account else '无'} → {next_acc.alias}"
    )
    try:
        ok = ensure_login_with_pool(tab, next_acc)
        if ok:
            _sync_reply_browser_cookies(
                reply_browser_instance,
                next_acc.cookies,
                label=f"账号 {next_acc.alias}",
                account_id=next_acc.account_id,
                account_alias=next_acc.alias,
            )
            if task_id:
                _task_mgr.bind_account(task_id, next_acc.account_id, next_acc.alias)
            return next_acc
        logger.warning(f"轮换账号 {next_acc.alias!r} 登录失败，继续使用当前账号")
    except Exception as e:
        logger.warning(f"账号轮换异常: {e}")
    return None


def _sync_reply_browser_cookies(
    reply_browser_instance,
    cookies: list[dict],
    *,
    label: str,
    account_id: str | None = None,
    account_alias: str | None = None,
) -> None:
    """将搜索侧确认可用的登录 Cookie 同步给评论专用浏览器实例。"""
    if reply_browser_instance is None:
        return
    normalized = [
        cookie
        for cookie in (cookies or [])
        if isinstance(cookie, dict) and cookie.get("name")
    ]
    if not normalized:
        logger.warning(f"{label} 登录已确认，但没有可同步到评论浏览器的 Cookie")
        return
    try:
        reply_browser_instance.set_cookies(
            normalized,
            account_id=account_id,
            account_alias=account_alias,
        )
        logger.info(f"已将 {label} 的 {len(normalized)} 条 Cookie 同步到评论浏览器实例")
    except Exception as e:
        logger.warning(f"同步 {label} Cookie 到评论浏览器实例失败: {e}")


def search(
    keyword: str,
    product: ProductType = "Top",
    timeout: Optional[float] = None,
    task_id: Optional[str] = None,
    resume: bool = True,
    fetch_replies: bool = False,
    max_replies_per_tweet: int = 20,
    reply_depth: int = 2,
    crawl_strategy: CrawlStrategy = "dfs",  # 保留参数兼容旧调用，统一走 DFS
    existing_tab=None,
    _time_split_context: Optional[dict] = None,
    browser_instance=None,
    reply_browser_instance=None,
    slot_id: Optional[int] = None,
    exclude_ids: Optional[set[str]] = None,
    recrawl_mode: bool = False,
    seed_tweets: Optional[list[dict]] = None,
    time_split_mode: str = "inherit",
    time_split_window_days: Optional[int] = None,
    time_split_max_segments: Optional[int] = None,
) -> SearchResult:
    """
    搜索 X 推文（含断点续爬 + 可选回复抓取 + 可暂停/可终止）

    Args:
        keyword:               搜索关键词
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
    all_tweets: list[dict] = list(seed_tweets or [])
    seen_ids: set[str] = {
        str(t.get("id") or "").strip()
        for t in all_tweets
        if str(t.get("id") or "").strip()
    }
    if exclude_ids:
        seen_ids.update(exclude_ids)
    _exclude_count = len(seen_ids)  # 复爬时预加载的排除 ID 数
    start_cursor: Optional[str] = None
    page_fetched: int = 0
    resumed = False
    _all_failed_records: list[dict] = []  # 收集所有失败的回复记录
    _last_bottom_cursor: Optional[str] = None  # 追踪最后有效 cursor，用于兜底保存
    _consecutive_empty_pages: int = 0  # 连续空页（API 返回 0 条新推文）计数
    # ── 复爬模式自动检测：有 exclude_ids 即为复爬，降低空页容忍加速跳过 ──
    _recrawl_mode = bool(exclude_ids) or bool(recrawl_mode)
    _MAX_CONSECUTIVE_EMPTY_PAGES: int = 2 if _recrawl_mode else 5
    _crawl_start_time = time.monotonic()
    _long_rest_done_at = 0.0  # 上次长休息时间戳
    ckpt: Optional[dict] = None
    _split_config = resolve_task_time_split(
        platform="x",
        keyword=keyword,
        start_date=None,
        end_date=None,
        time_split_mode=time_split_mode,
        time_split_window_days=time_split_window_days,
        time_split_max_segments=time_split_max_segments,
    )

    time_split_active = bool(_time_split_context)
    segment_prefix = ""
    segment_progress = None
    parent_tweets: list[dict] = []
    if time_split_active:
        current_segment = _time_split_context.get("current_segment", {})
        current_segment_index = int(_time_split_context.get("current_segment_index", 0))
        segments = _time_split_context.get("segments", [])
        total_segments = len(segments)
        parent_tweets = list(_time_split_context.get("parent_tweets", []))
        segment_progress = _build_segment_progress(
            enabled=True,
            total_segments=total_segments,
            completed_segments=int(_time_split_context.get("completed_segments", 0)),
            current_segment_index=current_segment_index + 1,
            current_since=current_segment.get("since"),
            current_until=current_segment.get("until"),
        )
        segment_prefix = (
            f"时间分段 {current_segment_index + 1}/{total_segments} "
            f"[{current_segment.get('since')} ~ {current_segment.get('until')}] · "
        )

    def _combine_for_task(segment_tweets: list[dict]) -> list[dict]:
        if not time_split_active:
            return segment_tweets
        return _merge_tweets_by_id(parent_tweets, segment_tweets)

    def _save_search_checkpoint(
        tweets_so_far: list[dict],
        next_cursor: Optional[str],
        page_fetched_to_save: int,
        *,
        sync: bool = False,
        force: bool = False,  # 新增 force 参数，任务结束时强制保存
    ) -> None:
        """保存 checkpoint，支持节流（每 3 秒最多保存一次）"""
        nonlocal _last_checkpoint_persist

        # 同步模式或强制模式：立即保存
        if sync or force:
            extra = _build_checkpoint_extra(tweets_so_far)
            _save = save_checkpoint_sync if sync else save_checkpoint
            _save(
                task_id=task_id,
                keyword=_search_keyword,
                product=_search_product,
                tweets_count=len(tweets_so_far),
                next_cursor=next_cursor,
                page_fetched=page_fetched_to_save,
                extra=extra,
            )
            _last_checkpoint_persist = time.monotonic()
            return

        # 节流：距上次保存 <3s 时跳过
        now = time.monotonic()
        if now - _last_checkpoint_persist < _PROGRESS_THROTTLE_SEC:
            return

        _last_checkpoint_persist = now
        extra = _build_checkpoint_extra(tweets_so_far)
        save_checkpoint(
            task_id=task_id,
            keyword=_search_keyword,
            product=_search_product,
            tweets_count=len(tweets_so_far),
            next_cursor=next_cursor,
            page_fetched=page_fetched_to_save,
            extra=extra,
        )

    def _build_checkpoint_extra(tweets_so_far: list[dict]) -> Optional[dict]:
        extra = None
        if time_split_active:
            extra = {
                "mode": "time_split",
                "root_keyword": _time_split_context.get("root_keyword", keyword),
                "base_query": _time_split_context.get("base_query", ""),
                "segments": _time_split_context.get("segments", []),
                "current_segment_index": int(
                    _time_split_context.get("current_segment_index", 0)
                ),
                "aggregated_tweets": _combine_for_task(tweets_so_far),
                "segment_progress": segment_progress or {},
            }
        return extra

    def _update_phase(message: str) -> None:
        if not task_id:
            return
        if segment_progress:
            _task_mgr.update_task_segment_progress(task_id, segment_progress)
        _task_mgr.update_task_phase(
            task_id, f"{segment_prefix}{message}" if segment_prefix else message
        )

    _last_progress_persist: float = 0.0  # checkpoint 节流计时器
    _PROGRESS_THROTTLE_SEC = 3.0  # 最低写入间隔
    _last_checkpoint_persist: float = 0.0  # checkpoint 单独节流计时器

    # ── Pipeline 模式：fetch_replies=True 时启用双 Tab 并发 ──────────
    _pipeline = None
    if fetch_replies:
        from crawler.pipeline import CrawlPipeline

        def _on_reply_done_pipeline(tweet_id_cb: str, replies_cb: list[dict]):
            """pipeline reply worker 每条完成后的落盘回调"""
            if task_id:
                _task_mgr.update_task_reply_snapshot(task_id, tweet_id_cb, replies_cb)

        _pipeline = CrawlPipeline(
            task_id=task_id,
            timeout=timeout,
            max_replies_per_tweet=max_replies_per_tweet,
            reply_depth=reply_depth,
            browser_instance=browser_instance,
            reply_browser_instance=reply_browser_instance,
            on_reply_done=_on_reply_done_pipeline,
        )

    def _update_progress(current_page: int, tweets_so_far: list[dict]) -> None:
        nonlocal _last_progress_persist
        if not task_id:
            return
        now = time.monotonic()
        # 节流：距上次落盘 <3s 时仅更新内存中的 preview
        if now - _last_progress_persist < _PROGRESS_THROTTLE_SEC:
            _task_mgr.update_preview_tweets(
                task_id, current_page, _combine_for_task(tweets_so_far)
            )
            return
        _last_progress_persist = now
        _task_mgr.update_task_progress(
            task_id, current_page, _combine_for_task(tweets_so_far)
        )
        if segment_progress:
            _task_mgr.update_task_segment_progress(task_id, segment_progress)

    def _update_preview(current_page: int, tweets_so_far: list[dict]) -> None:
        if not task_id:
            return
        _task_mgr.update_preview_tweets(
            task_id, current_page, _combine_for_task(tweets_so_far)
        )
        if segment_progress:
            _task_mgr.update_task_segment_progress(task_id, segment_progress)

    # ── 缓存时间分割计划，避免重复构建（原逻辑最多调用 3 次） ──
    _time_split_plan_cache = None

    def _get_time_split_plan():
        nonlocal _time_split_plan_cache
        if _time_split_plan_cache is None:
            _time_split_plan_cache = build_time_split_plan(
                keyword,
                enabled=_split_config.enabled,
                trigger_days=_split_config.trigger_days,
                window_days=_split_config.window_days,
                unlimited_window_days=_split_config.window_days,
                max_segments=_split_config.max_segments,
                force_window=_split_config.force_window,
            )
        return _time_split_plan_cache

    def _dispatch_time_splits():
        return _search_with_time_splits(
            keyword=keyword,
            product=product,
            timeout=timeout,
            task_id=task_id,
            resume=resume,
            fetch_replies=fetch_replies,
            max_replies_per_tweet=max_replies_per_tweet,
            reply_depth=reply_depth,
            crawl_strategy=crawl_strategy,
            browser_instance=browser_instance,
            reply_browser_instance=reply_browser_instance,
            slot_id=slot_id,
            exclude_ids=exclude_ids,
            recrawl_mode=_recrawl_mode,
            time_split_mode=time_split_mode,
            time_split_window_days=time_split_window_days,
            time_split_max_segments=time_split_max_segments,
        )

    logger.info(
        f"DEBUG: task_id={task_id}, resume={resume}, time_split_active={time_split_active}, "
        f"seed_tweets_count={len(seed_tweets) if seed_tweets else 0}, all_tweets_count={len(all_tweets)}, "
        f"_recrawl_mode={_recrawl_mode}"
    )
    if task_id and resume:
        ckpt = load_checkpoint(task_id)
        logger.info(
            f"DEBUG checkpoint: ckpt={'有' if ckpt else '无'}, "
            f"ckpt_keyword={ckpt.get('keyword') if ckpt else 'N/A'}, "
            f"ckpt_product={ckpt.get('product') if ckpt else 'N/A'}, "
            f"input_keyword={keyword}, input_product={product}"
        )
        
        # ── 检查是否需要时间分段（在 Recrawl 模式下优先级最高） ──
        # 情况 1：checkpoint 是时间分段模式
        if (
            not time_split_active
            and ckpt
            and ckpt.get("mode") == "time_split"
            and ckpt.get("root_keyword") == keyword
            and ckpt.get("product") == product
        ):
            return _search_with_time_splits(
                keyword=keyword,
                product=product,
                timeout=timeout,
                task_id=task_id,
                resume=resume,
                fetch_replies=fetch_replies,
                max_replies_per_tweet=max_replies_per_tweet,
                reply_depth=reply_depth,
                crawl_strategy=crawl_strategy,
                checkpoint=ckpt,
                browser_instance=browser_instance,
                reply_browser_instance=reply_browser_instance,
                slot_id=slot_id,
                exclude_ids=exclude_ids,
                recrawl_mode=_recrawl_mode,
                time_split_mode=time_split_mode,
                time_split_window_days=time_split_window_days,
                time_split_max_segments=time_split_max_segments,
            )
        
        # 情况 2：Recrawl 模式 + checkpoint keyword 不匹配 → 说明是时间分段任务，需要重新分段
        if (
            not time_split_active
            and _recrawl_mode
            and ckpt
            and ckpt.get("keyword") != keyword
        ):
            if _get_time_split_plan().enabled:
                logger.info(
                    f"Recrawl 时间分段任务：checkpoint keyword 不匹配（{ckpt.get('keyword')} != {keyword}），"
                    f"启动时间分段重新爬取"
                )
                return _dispatch_time_splits()
        
        # 情况 3：普通模式，checkpoint 不匹配，检查是否需要启用时间分段
        if not time_split_active and not (
            ckpt and ckpt.get("keyword") == keyword and ckpt.get("product") == product
        ):
            if _get_time_split_plan().enabled:
                logger.info(f"启用时间分段：task_id={task_id}")
                return _dispatch_time_splits()
        if ckpt and ckpt.get("keyword") == keyword and ckpt.get("product") == product:
            all_tweets = ckpt.get("tweets", [])
            seen_ids = {t["id"] for t in all_tweets if t.get("id")}
            start_cursor = ckpt.get("next_cursor")
            page_fetched = ckpt.get("page_fetched", 0)
            resumed = True
            logger.info(
                f"从断点恢复：task_id={task_id}，"
                f"已有 {len(all_tweets)} 条，cursor={'有' if start_cursor else '无'}，"
                f"_recrawl_mode={_recrawl_mode}"
            )

            # ── 无 cursor 时的分支处理 ──
            if not start_cursor:
                logger.info(
                    f"断点恢复（无 cursor）：保留 {len(all_tweets)} 条旧推文用于去重，开始从头检查是否有新增内容"
                )
                page_fetched = 0
                if _recrawl_mode:
                    _MAX_CONSECUTIVE_EMPTY_PAGES = 10
                    logger.info(f"recrawl 从头搜索：空页容忍度提高到 {_MAX_CONSECUTIVE_EMPTY_PAGES}")

    if task_id and not time_split_active and ckpt is None:
        if _get_time_split_plan().enabled:
            return _dispatch_time_splits()

    # ── 2. 启动浏览器标签页 ─────────────────────────────────────────
    if existing_tab is not None:
        tab = existing_tab
    elif browser_instance is not None:
        tab = browser_instance.new_tab()
    else:
        tab = get_new_tab()
    owns_tab = existing_tab is None
    try:
        # ── 账号池初始化：若启用账号池且有账号，优先使用账号池登录 ──
        pool = get_pool()
        account_pool_enabled = getattr(settings, "account_pool_enabled", True)
        current_account = None

        if account_pool_enabled and pool.get_active_account_count() > 0:
            bound_account_id = None
            if task_id:
                bound_account_id, _ = _task_mgr.get_task_account(task_id)
            if bound_account_id:
                current_account = pool.get_account(bound_account_id)
            else:
                current_account = (
                    pool.pick_account_by_index(slot_id)
                    if slot_id is not None
                    else pool.pick_next_account()
                )
            if current_account:
                account_login = ensure_login_with_pool_detailed(tab, current_account)
                if not account_login.ok:
                    # Cloudflare challenge 不是账号问题，回退默认登录也没用，直接暂停
                    if account_login.reason == "challenge_required":
                        raise LoginRequiredPause(
                            _build_login_pause_message(account_login),
                            reason=account_login.reason,
                            session_mode=account_login.session_mode,
                            effective_user_data_path=account_login.effective_user_data_path,
                        )
                    logger.warning(
                        f"账号池首账号 {current_account.alias!r} 登录失败，"
                        f"reason={account_login.reason}，回退至默认登录"
                    )
                    current_account = None
                else:
                    if task_id and bound_account_id != current_account.account_id:
                        _task_mgr.bind_account(
                            task_id, current_account.account_id, current_account.alias
                        )
                    _sync_reply_browser_cookies(
                        reply_browser_instance,
                        current_account.cookies,
                        label=f"账号 {current_account.alias}",
                        account_id=current_account.account_id,
                        account_alias=current_account.alias,
                    )
                    logger.info(
                        f"使用账号池登录: {current_account.alias!r}，"
                        f"活跃账号数: {pool.get_active_account_count()}"
                    )

        # 账号池未启用或账号池为空，走原有 ensure_login
        if current_account is None:
            login_result = ensure_login_detailed(tab)
            if not login_result.ok:
                raise LoginRequiredPause(
                    _build_login_pause_message(login_result),
                    reason=login_result.reason,
                    session_mode=login_result.session_mode,
                    effective_user_data_path=login_result.effective_user_data_path,
                )
            _sync_reply_browser_cookies(
                reply_browser_instance,
                load_cookies(),
                label="持久化 X 登录态",
            )

        search_url = _build_search_url(keyword, product)
        logger.info(
            f"开始搜索: keyword='{keyword}', product={product}, "
            f"strategy=unified_dfs, fetch_replies={fetch_replies}, 从断点={resumed}, "
            f"高级搜索={'是' if _has_search_operators(keyword) else '否'}, "
            f"排除已有={_exclude_count if _exclude_count else 0}, "
            f"账号={'池(' + str(pool.get_active_account_count()) + '个)' if current_account else '默认'}"
        )
        telemetry.record_event(
            task_id,
            "search_started",
            status="running",
            phase="搜索任务已开始",
            meta={"keyword": keyword, "product": product, "resumed": resumed},
        )

        # ── 3. 开启监听 ─────────────────────────────────────────────
        tab.listen.start(SEARCH_TIMELINE_PATTERN, max_record=50)  # 限制缓存上限

        # ── 4. 访问搜索页面（含错误页自动刷新）───────────────────────────
        # X 的搜索框原生支持高级语法（如 since:、from:、min_faves: 等）
        # 直接导航到完整 URL 即可，无需分阶段预热
        try:
            ok = _navigate_direct(
                tab=tab,
                search_url=search_url,
                policy=policy,
                task_id=task_id,
            )
        except SplashTimeoutSignal as splash_e:
            # 黑屏持续无法恢复，尝试切换账号后重新导航
            logger.warning(f"{splash_e}，尝试切换账号...")
            rotated = _try_rotate_account(
                tab,
                current_account,
                pool,
                "splash_timeout",
                reply_browser_instance=reply_browser_instance,
                task_id=task_id,
            )
            if rotated:
                current_account = rotated
                logger.info(f"已切换到账号 {rotated.alias!r}，重新导航搜索页面")
                ok = _navigate_direct(
                    tab=tab,
                    search_url=search_url,
                    policy=policy,
                    task_id=task_id,
                )
            else:
                logger.warning("无可用备用账号，继续使用当前账号（页面可能仍黑屏）")
                ok = False

        if not ok:
            raise RuntimeError(f"搜索页面反复出现错误，无法加载: {search_url}")

        # 记录浏览器实际 URL（用于调试 URL 编码问题）
        try:
            actual_url = tab.url
            logger.info(f"浏览器实际 URL: {actual_url}")
        except Exception:
            pass

        page_num = page_fetched + 1
        _cursor_only_streak = 0  # cursor-only 包连续计数器
        _MAX_CURSOR_ONLY_STREAK = 3  # 连续 3 个 cursor-only 包后强制翻页或停止

        while True:
            # 每页开始前检查控制信号
            check_signal(task_id)

            logger.info(f"等待第 {page_num} 页数据包（timeout={timeout}s）...")
            if task_id:
                _update_phase(f"等待第 {page_num} 页数据包...")
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
                # 只有本次运行已获取过数据（page_num > 1）才启用"到底"检测
                # 避免断点恢复时 all_tweets 有旧数据导致误判
                fetched_count=page_num - 1,
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

            # ── 搜索无结果：立即结束当前时间段 ───────────────────────
            if packet is _NO_RESULTS_SENTINEL:
                logger.info(f"第 {page_num} 页搜索无结果（No results），结束当前搜索")
                if task_id:
                    _update_phase("当前时间段无搜索结果，准备跳到下一段")
                    telemetry.record_event(
                        task_id,
                        "search_no_results",
                        status="running",
                        phase="当前时间段无搜索结果",
                        page=page_num,
                    )
                break

            # ── 时间线到底：当前时间段已无更多内容 ─────────────────────
            if packet is _END_OF_TIMELINE_SENTINEL:
                logger.info(f"第 {page_num} 页时间线已到底部，结束当前搜索")
                if task_id:
                    _update_phase("当前时间段已到底部，准备跳到下一段")
                    telemetry.record_event(
                        task_id,
                        "search_end_of_timeline",
                        status="running",
                        phase="当前时间段已到底部",
                        page=page_num,
                    )
                break

            try:
                body = extract_packet_body_dict(packet)
                if not isinstance(body, dict):
                    logger.debug(f"非 JSON 响应，跳过（url={packet.url[:80]}）")
                    continue

                # 保存原始搜索响应
                if task_id:
                    save_raw_response(task_id, page_num, body)

                tweets_page, bottom_cursor, _ = parse_search_response(body)
                if bottom_cursor:
                    _last_bottom_cursor = bottom_cursor  # 追踪最后有效 cursor

                if not tweets_page and bottom_cursor:
                    _cursor_only_streak += 1
                    logger.info(
                        f"第 {page_num} 页收到仅游标 SearchTimeline 包（连续 {_cursor_only_streak}/{_MAX_CURSOR_ONLY_STREAK}），继续等待当前页真实结果"
                    )
                    telemetry.record_event(
                        task_id,
                        "search_cursor_only_packet",
                        status="running",
                        phase=f"第 {page_num} 页收到仅游标数据包（连续 {_cursor_only_streak}），继续等待真实结果",
                        page=page_num,
                    )
                    # 连续多个 cursor-only 包：可能是 X 的异常响应，强制翻页
                    if _cursor_only_streak >= _MAX_CURSOR_ONLY_STREAK:
                        logger.warning(
                            f"连续 {_MAX_CURSOR_ONLY_STREAK} 个 cursor-only 包，"
                            f"可能是 X 异常响应，尝试滚动触发新请求"
                        )
                        try:
                            tab.scroll.down(500)
                            jittered_sleep(1.5, task_id=task_id)
                        except Exception as scroll_err:
                            logger.debug(f"滚动失败: {scroll_err}")
                        _cursor_only_streak = 0  # 重置计数器
                    continue
                else:
                    # 收到真实数据，重置计数器
                    _cursor_only_streak = 0

                # 去重
                new_tweets = [t for t in tweets_page if t.get("id") not in seen_ids]
                for t in new_tweets:
                    seen_ids.add(t.get("id", ""))

                # ── 连续空页检测 ────────────────────────────────────────
                if not new_tweets:
                    _consecutive_empty_pages += 1
                    bump_metric(task_id, "empty_pages")
                    if _consecutive_empty_pages >= _MAX_CONSECUTIVE_EMPTY_PAGES:
                        logger.info(
                            f"连续 {_MAX_CONSECUTIVE_EMPTY_PAGES} 页无新推文，"
                            f"当前时间段搜索结果已耗尽，停止翻页"
                        )
                        if task_id:
                            _update_phase("连续多页无新推文，结束当前搜索")
                        break
                    logger.info(
                        f"第 {page_num} 页无新推文（连续空页 {_consecutive_empty_pages}/{_MAX_CONSECUTIVE_EMPTY_PAGES}），继续翻页"
                    )
                else:
                    _consecutive_empty_pages = 0

                # ── 模拟人类阅读：慢慢浏览本页推文 ────────────────────
                # 当 DFS 回复抓取启用时跳过模拟阅读，回复抓取本身已提供足够的自然延迟
                # 复爬模式也跳过模拟阅读，全速推进
                # 并发模式（pool_mode）也跳过：动态间隔已充分控制速率
                _pool_mode_active = browser_instance is not None
                if new_tweets and not fetch_replies and not _recrawl_mode and not _pool_mode_active:
                    simulate_reading(tab, task_id=task_id, tweet_count=len(new_tweets))

                # ── 每批新推文立即抓取回复（统一 DFS / Pipeline 策略） ──────
                if fetch_replies and new_tweets:
                    if _pipeline is not None:
                        # ── Pipeline 模式：搜索 tab 不停监听，回复在 reply_tab 并发抓取 ──
                        logger.info(
                            f"[Pipeline] 第 {page_num} 页 {len(new_tweets)} 条推文放入流水线..."
                        )
                        if task_id:
                            _update_phase(
                                f"[Pipeline] 第 {page_num} 页 {len(new_tweets)} 条推文已入队，并发抓回复中..."
                            )
                            _update_preview(page_num, list(all_tweets) + new_tweets)
                            # 搜索侧立即落盘 checkpoint（不等回复）
                            _save_search_checkpoint(
                                list(all_tweets) + new_tweets, bottom_cursor, page_num
                            )

                        # 启动 pipeline（仅在第一批时启动）
                        if not _pipeline._reply_thread:
                            _pipeline.start()

                        _pipeline.put_batch(new_tweets)

                        # 检查 reply worker 是否发生了致命错误（非阻塞）
                        reply_err = _pipeline.get_error()
                        if reply_err is not None:
                            raise reply_err

                    else:
                        # ── Legacy DFS 模式（fetch_replies=False 时不会走这里，保留安全路径） ──
                        logger.info(f"立即抓取 {len(new_tweets)} 条新推文的回复...")

                        if task_id:
                            _update_phase(
                                f"第 {page_num} 页已解析 {len(new_tweets)} 条，正在抓取回复..."
                            )
                            _update_preview(page_num, list(all_tweets) + new_tweets)
                            _save_search_checkpoint(
                                list(all_tweets) + new_tweets, bottom_cursor, page_num
                            )

                        tab.listen.stop()

                        _dfs_all_tweets_ref = all_tweets
                        _dfs_processed: list[dict] = []
                        _dfs_tweet_index = {t.get("id", ""): t for t in new_tweets}
                        _dfs_reply_progress_counter = 0

                        def _on_reply_progress(tweet_id: str, replies: list[dict]):
                            nonlocal _dfs_reply_progress_counter
                            _dfs_reply_progress_counter += 1
                            orig = _dfs_tweet_index.get(tweet_id)
                            if orig is not None:
                                processed_tweet = dict(orig)
                                processed_tweet["replies"] = replies
                                _dfs_processed.append(processed_tweet)
                            if task_id:
                                _task_mgr.update_task_reply_snapshot(
                                    task_id, tweet_id, replies
                                )
                                interim_tweets = list(_dfs_all_tweets_ref) + list(
                                    _dfs_processed
                                )
                                flushed = stage_reply_checkpoint(
                                    task_id=task_id,
                                    keyword=_search_keyword,
                                    product=_search_product,
                                    tweets_so_far=interim_tweets,
                                    next_cursor=bottom_cursor,
                                    page_fetched=page_num,
                                    extra=_build_checkpoint_extra(interim_tweets),
                                )
                                if flushed:
                                    _update_progress(page_num, interim_tweets)

                        try:
                            new_tweets, _dfs_failed = _fetch_replies_for_tweets(
                                new_tweets,
                                max_replies_per_tweet,
                                task_id,
                                timeout,
                                strategy="dfs",
                                progress_callback=_on_reply_progress,
                                reply_depth=reply_depth,
                                browser_instance=browser_instance,
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
                            if e.partial_tweets:
                                all_tweets.extend(e.partial_tweets)
                            if task_id:
                                _update_progress(page_num, list(all_tweets))
                                _save_search_checkpoint(
                                    list(all_tweets), bottom_cursor, page_num
                                )
                            raise
                        finally:
                            tab.listen.start(SEARCH_TIMELINE_PATTERN, max_record=50)  # 限制缓存上限
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

                # 清理已处理的缓存包，防止堆积
                try:
                    tab.listen.clear()
                except Exception:
                    pass

                # 写检查点（每页立即保存）
                if task_id:
                    _save_search_checkpoint(all_tweets, bottom_cursor, page_num)
                    _update_progress(page_num, list(all_tweets))
                    _update_phase(
                        f"已完成第 {page_num} 页，共 {len(_combine_for_task(all_tweets))} 条"
                    )

                if not bottom_cursor:
                    logger.info("无更多数据（bottom_cursor 为空），停止")
                    break
                # ── 休息节律（大幅缩减，仅保留必要的反风控节奏） ──────────
                # 复爬模式全速推进：跳过所有休息节律
                # 并发模式（pool_mode）下也跳过：多任务并行时每个任务各自独占账号，
                # 动态间隔已充分控制速率，额外休息只会拖慢整体吞吐
                _pool_mode_active = browser_instance is not None
                if (
                    getattr(settings, "crawler_enable_break_rhythm", True)
                    and new_tweets
                    and not _recrawl_mode
                    and not _pool_mode_active
                ):
                    _total_fetched_now = len(all_tweets)
                    # 微休息（1% 概率，1-2 秒）
                    if random.random() < 0.01:
                        _micro_wait = random.uniform(1, 2)
                        logger.info(f"微休息 {_micro_wait:.0f}s...")
                        if task_id:
                            _update_phase(f"微休息中 ({_micro_wait:.0f}s)，稍后继续...")
                        interruptible_sleep(_micro_wait, task_id=task_id)
                    # 小憩（每 2000 条推文，5-10 秒）
                    _short_n = max(
                        2000, getattr(settings, "crawler_short_break_every_n", 500) * 4
                    )
                    if _short_n > 0 and _total_fetched_now > 0:
                        prev_count = _total_fetched_now - len(new_tweets)
                        if prev_count // _short_n < _total_fetched_now // _short_n:
                            _short_wait = random.uniform(5, 10)
                            logger.info(
                                f"小憩 {_short_wait:.0f}s（累计 {_total_fetched_now} 条）..."
                            )
                            if task_id:
                                _update_phase(
                                    f"小憩中 ({_short_wait:.0f}s)，稍后继续..."
                                )
                            interruptible_sleep(_short_wait, task_id=task_id)
                    # 长休息（每 6 小时，30-60 秒）
                    _rest_h = max(
                        6.0,
                        getattr(settings, "crawler_long_rest_interval_hours", 4.0) * 1.5,
                    )
                    _rest_interval = _rest_h * 3600 * random.uniform(0.90, 1.10)
                    _now_mono = time.monotonic()
                    _last_rest = max(_crawl_start_time, _long_rest_done_at)
                    if _now_mono - _last_rest >= _rest_interval:
                        _long_wait = random.uniform(30, 60)
                        logger.info(
                            f"长休息 {_long_wait:.0f}s（运行 {(_now_mono - _crawl_start_time) / 3600:.1f}h）..."
                        )
                        if task_id:
                            _update_phase(
                                f"长休息中 ({_long_wait:.0f}s)，稍后继续..."
                            )
                        interruptible_sleep(_long_wait, task_id=task_id)
                        _long_rest_done_at = time.monotonic()

            except StopSignal:
                raise
            except ChallengeSignal:
                raise
            except SplashTimeoutSignal as splash_e:
                # 主循环中页面持续黑屏，尝试换账号后重新导航继续
                logger.warning(f"主循环检测到黑屏信号：{splash_e}，尝试切换账号...")
                bump_metric(task_id, "splash_account_rotations")
                rotated = _try_rotate_account(
                    tab,
                    current_account,
                    pool,
                    "splash_in_loop",
                    reply_browser_instance=reply_browser_instance,
                    task_id=task_id,
                )
                if rotated:
                    current_account = rotated
                    logger.info(f"已切换到账号 {rotated.alias!r}，重新导航搜索页面继续采集")
                    try:
                        tab.listen.stop()
                    except Exception:
                        pass
                    tab.listen.start(SEARCH_TIMELINE_PATTERN, max_record=50)  # 限制缓存上限
                    _navigate_direct(
                        tab=tab,
                        search_url=search_url,
                        policy=policy,
                        task_id=task_id,
                    )
                else:
                    logger.warning("无可用备用账号，跳过黑屏恢复，继续等待下一页")
                # 不 break，继续采集循环
            except Exception as e:
                logger.error(f"第 {page_num} 页解析失败: {e}", exc_info=True)
                break

            # 人性化渐进滚动翻页（模拟人类浏览行为）
            page_num += 1

            # ── 搜索账号切换：仅在速率压力过高时紧急切换（不主动轮换）──
            # 搜索由单账号贯穿完成；只有 rate_multiplier 超阈值时才紧急换人
            _rotation_threshold = getattr(
                settings, "account_rotation_multiplier_threshold", 2.0
            )
            _pool_enabled = getattr(settings, "account_pool_enabled", True)
            if _pool_enabled and pool.total_count() > 1 and current_account:
                _rate_mult = get_tracker().get_sleep_multiplier(
                    "search", task_id=task_id
                )
                if _rate_mult >= _rotation_threshold:
                    rotated = _try_rotate_account(
                        tab,
                        current_account,
                        pool,
                        f"搜索速率倍数 {_rate_mult:.1f} 超阈值 {_rotation_threshold}，紧急切换",
                        reply_browser_instance=reply_browser_instance,
                        task_id=task_id,
                    )
                    if rotated:
                        current_account = rotated
                        # 切换后 seen_ids 保持不变，新账号继续去重搜索

            # ── 动态间隔：根据账号数 + rate_multiplier 计算等待时间 ──
            _rate_mult = get_tracker().get_sleep_multiplier("search", task_id=task_id)
            min_s, max_s, _ = compute_dynamic_interval("search")
            # 滚动本身已耗时 ~1s，打折后仅补足差值
            _scroll_overhead = 1.0
            _sleep_time = max(
                0.3, random.uniform(min_s, max_s) * _rate_mult - _scroll_overhead
            )
            logger.debug(
                f"翻页间隔: {_sleep_time:.1f}s "
                f"(动态区间 {min_s:.1f}~{max_s:.1f}s × rate_mult {_rate_mult:.1f})"
            )
            interruptible_sleep(_sleep_time, task_id=task_id)

            telemetry.record_event(
                task_id,
                "search_scroll_next_page",
                status="running",
                phase=f"准备进入第 {page_num} 页，执行滚动翻页",
                page=page_num,
            )
            if task_id:
                _update_phase(f"正在滚动进入第 {page_num} 页...")
            human_like_scroll(tab, task_id=task_id)

    finally:
        if task_id:
            flush_reply_checkpoint(task_id)
            clear_reply_checkpoint(task_id)

        # ── Pipeline 收尾：等待 reply worker 耗尽队列 ─────────────────
        if _pipeline is not None:
            if _pipeline._reply_thread is not None:
                # 搜索已结束，发送结束哨兵并等待 reply worker 完成
                _pipeline.finish_search()
                _pipeline.join()
                # 将 pipeline 中已完成的回复合并回 all_tweets
                for i, tweet in enumerate(all_tweets):
                    tid = str(tweet.get("id", ""))
                    if tid in _pipeline.result_map:
                        all_tweets[i] = _pipeline.result_map[tid]
                _all_failed_records.extend(_pipeline.failed_records)
                logger.info(
                    f"[Pipeline] 搜索+回复全部完成，reply_map={len(_pipeline.result_map)} 条，"
                    f"failed={len(_pipeline.failed_records)} 条"
                )
            else:
                # pipeline 从未启动（0 条推文需要回复）
                pass

        # ── 安全兜底：无论何种原因退出，都尝试保存已采集数据 ──
        if task_id and all_tweets:
            try:
                _save_search_checkpoint(all_tweets, _last_bottom_cursor, page_num, sync=True)
                _update_progress(page_num, list(all_tweets))
                logger.info(
                    f"安全兜底保存: {len(all_tweets)} 条推文已持久化"
                    f"（cursor={'有' if _last_bottom_cursor else '无'}）"
                )
            except Exception as e:
                logger.error(f"安全兜底保存失败: {e}")
        try:
            tab.listen.stop()
        except Exception:
            pass
        if owns_tab:
            try:
                tab.close()
            except Exception:
                pass

    # ── BFS 分支已移除：统一使用 DFS，每批搜索结果中已即时处理评论 ──

    # 搜索流程正常跑完后删除检查点，避免任务已完成却长期残留旧断点。
    if task_id:
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
    browser_instance=None,
) -> tuple[list[dict], list[dict]]:
    """统一的回复抓取入口（BFS/DFS 共用），返回 (updated_tweets, failed_records)"""
    from crawler.reply_fetcher import fetch_replies_batch

    def on_progress(tweet_id: str, replies: list[dict]):
        if task_id:
            _task_mgr.update_task_reply_snapshot(task_id, tweet_id, replies)
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
        browser_instance=browser_instance,
    )


def _count_replies(tweets: list[dict]) -> int:
    """统计推文列表中回复总数"""
    total = 0

    def _walk(nodes: list[dict]) -> None:
        nonlocal total
        for node in nodes:
            if not isinstance(node, dict):
                continue
            total += 1
            replies = node.get("replies") or []
            if isinstance(replies, list) and replies:
                _walk(replies)

    for tweet in tweets:
        replies = tweet.get("replies") or []
        if isinstance(replies, list) and replies:
            _walk(replies)
    return total


# ═══════════════════════════════════════════════════════════════════
#  导航策略
# ═══════════════════════════════════════════════════════════════════


def _navigate_direct(
    *,
    tab,
    search_url: str,
    policy,
    task_id: Optional[str],
) -> bool:
    """直接导航到搜索 URL（用于无高级操作符的简单搜索）。"""
    ok = navigate_with_retry(
        tab,
        search_url,
        max_retries=policy.refresh_max_retries,
        base_wait=3.0,
        load_timeout=30.0,
        post_load_wait=0.5,
        challenge_retry_times=policy.challenge_retry_times,
        challenge_cooldown=policy.challenge_cooldown,
        raise_on_risk=True,
        task_id=task_id,
    )
    if not ok:
        logger.warning(
            "搜索页首跳失败，执行预热路径后再重试一次（home -> explore -> search）"
        )
        try:
            tab.get("https://x.com/home", timeout=25)
            sleep_with_jitter(0.5, jitter_ratio=0.15, minimum=0.3)
            tab.get("https://x.com/explore", timeout=25)
            sleep_with_jitter(0.5, jitter_ratio=0.15, minimum=0.3)
        except Exception as warmup_err:
            logger.warning(f"搜索预热路径失败（忽略，继续最终重试）: {warmup_err}")

        ok = navigate_with_retry(
            tab,
            search_url,
            max_retries=max(1, policy.refresh_max_retries // 2),
            base_wait=4.0,
            load_timeout=35.0,
            post_load_wait=0.5,
            challenge_retry_times=policy.challenge_retry_times,
            challenge_cooldown=max(policy.challenge_cooldown, 10.0),
            raise_on_risk=True,
            task_id=task_id,
        )
    return ok


# ═══════════════════════════════════════════════════════════════════
#  URL 构建
# ═══════════════════════════════════════════════════════════════════


def _build_search_url(keyword: str, product: ProductType) -> str:
    """构建搜索 URL"""
    url = SEARCH_URL_TEMPLATE.format(query=quote(keyword)) + _TAB_MAP.get(product, "")
    logger.info(f"构建搜索 URL: {url}")
    return url
