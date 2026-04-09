"""
回复抓取器模块（v5 - 纯滚动翻页 + expected_count 参考）

变更（v5）：
- 根据抓包分析，确认 X 评论区翻页是纯滚动触发 TweetDetail API，无 "Show more" 按钮
- 删除 _click_show_more 及相关逻辑，简化翻页为：滚动 → 等待数据包 → 解析
- 保留渐进式多步滚动确保懒加载内容完全触发
- 保留快速退出、连续空页计数器、随机扰动等策略
"""
import logging
import random
import time
from typing import Optional

from crawler.auth import check_login, ensure_login_detailed, ensure_x_domain_context
from crawler.browser import get_new_tab, promote_browser_for_manual_interaction
from crawler.cookie_manager import _build_cookie_dict
from crawler.reply_parser import parse_tweet_detail_response, TWEET_DETAIL_PATTERN
from crawler.response_saver import save_reply_response
from crawler.page_health import navigate_with_retry
from crawler.page_state import detect_page_state, PageState, detect_reply_area_error, click_reply_retry_button
from crawler.packet_guard import wait_for_target_packet, is_tweet_detail_body, extract_packet_body_dict
from crawler.recovery_policy import (
    RecoveryPolicy,
    backoff_seconds,
    sleep_with_jitter,
    build_challenge_wait_plan,
    wait_for_challenge,
)
from crawler.crawl_signals import StopSignal, ChallengeSignal, SplashTimeoutSignal, RiskState
from crawler.utils import jittered_sleep, check_signal, merge_remaining, interruptible_sleep
from crawler.scroll_safe import safe_scroll_down, safe_scroll_up, safe_scroll_to_bottom
from crawler.runtime_metrics import bump_metric
from crawler.rate_tracker import get_tracker, extract_rate_headers
from crawler import telemetry
from crawler.wait_policy import (
    quick_probe_timeout,
    compensation_probe_timeout,
    before_scroll_wait,
    scroll_steps,
    scroll_step_pause,
)
from config import settings

logger = logging.getLogger(__name__)

# 连续无新评论的最大重试次数（超过后认为评论区已到底）
_MAX_EMPTY_PAGES = 3


def _dynamic_max_empty_pages(expected_count: int) -> int:
    """根据预期评论数动态调整连续空页退出阈值。

    大评论量推文的评论区翻页更容易出现重复数据导致的"假空页"，
    需要更大的容忍度才能触发更多真实加载。
    """
    if expected_count <= 50:
        return _MAX_EMPTY_PAGES  # 3
    if expected_count <= 500:
        return 5
    if expected_count <= 2000:
        return 8
    return 12

# ── 登录验证 TTL 缓存 ────────────────────────────────────────
# 同一 tab 在 TTL 内跳过重复的登录检查和域切换
_LOGIN_CHECK_TTL = 120.0  # 秒

import threading
_login_cache_lock = threading.Lock()
# key: tab id → {"verified_at": float}
_login_cache: dict[int, dict] = {}


def _is_login_cached(tab) -> bool:
    """检查 tab 的登录验证缓存是否仍然有效。"""
    tab_id = id(tab)
    with _login_cache_lock:
        entry = _login_cache.get(tab_id)
        if entry and (time.monotonic() - entry["verified_at"]) < _LOGIN_CHECK_TTL:
            return True
    return False


def _mark_login_cached(tab) -> None:
    """标记 tab 的登录验证通过时间。"""
    tab_id = id(tab)
    with _login_cache_lock:
        _login_cache[tab_id] = {"verified_at": time.monotonic()}


def _invalidate_login_cache(tab) -> None:
    """使 tab 的登录缓存失效。"""
    tab_id = id(tab)
    with _login_cache_lock:
        _login_cache.pop(tab_id, None)


def _safe_stop_listener(tab) -> None:
    from crawler.tab_guard import safe_stop_listener
    safe_stop_listener(tab)


def _to_risk_state(state: PageState) -> RiskState:
    if state == PageState.RATE_LIMITED:
        return "rate_limited"
    if state == PageState.LOGIN_REQUIRED:
        return "login_required"
    return "challenge"


# ═══════════════════════════════════════════════════════════════════
#  翻页辅助函数
# ═══════════════════════════════════════════════════════════════════


def _scroll_incremental(tab, *, task_id: Optional[str] = None, steps: Optional[int] = None) -> None:
    """
    评论区渐进式滚动：快速滚动触发懒加载。

    优化后：2 步快速滚动 + 最后 scroll_to_bottom，总耗时 <1s。
    """
    move_steps = steps if steps is not None else 2
    for i in range(move_steps):
        px = random.randint(200, 450)
        safe_scroll_down(tab, px, task_id=task_id)

        # 极短停顿
        scroll_step_pause(task_id=task_id)

    # 最后滚到底部确保触发评论懒加载
    safe_scroll_to_bottom(tab, task_id=task_id)


def _wait_reply_packet_with_recovery(
    *,
    tab,
    timeout: float,
    page_num: int,
    tweet_url: str,
    task_id: Optional[str],
    policy: RecoveryPolicy,
    on_reply_area_error_switch_account=None,
):
    """等待 TweetDetail 数据包，超时时执行软恢复与硬刷新。

    翻页策略：X 评论区由滚动触发 TweetDetail API。
    快速探测未命中时，立即再次滚动到底部重新触发，比纯等待更高效。

    on_reply_area_error_switch_account: 可选回调，连续点击 Retry 按钮无效时调用触发换账号。
    """
    # 断路器：错误风暴时等待统一冷却
    from crawler.circuit_breaker import get_breaker
    get_breaker().acquire_permission(task_id)

    risk_hits = 0
    reply_area_retry_hits = 0  # 评论区局部错误连续点击 Retry 次数
    _REPLY_AREA_RETRY_SWITCH_THRESHOLD = 3  # 连续 3 次点击无效后换账号
    probe_timeout = quick_probe_timeout(timeout)
    packet, ignored = wait_for_target_packet(
        tab,
        timeout=probe_timeout,
        accept_body=is_tweet_detail_body,
    )
    if packet:
        if ignored:
            logger.debug(f"  回复第 {page_num} 页快速探测过滤无关包 {ignored} 个")
        _update_reply_rate_tracker(packet, task_id=task_id)
        return packet

    for soft_attempt in range(policy.packet_soft_retries + 1):
        # 快探超时说明滚动可能没触发加载，补一次完整滚动再等
        _scroll_incremental(tab, task_id=task_id)

        packet, ignored = wait_for_target_packet(
            tab,
            timeout=compensation_probe_timeout(timeout),
            accept_body=is_tweet_detail_body,
        )
        if packet:
            if ignored:
                logger.debug(f"  回复第 {page_num} 页过滤无关包 {ignored} 个")
            _update_reply_rate_tracker(packet, task_id=task_id)
            return packet
        bump_metric(task_id, "reply_packet_timeouts")
        get_breaker().record_error(task_id)

        # ── 评论区局部加载错误检测（"出错了。请尝试重新加载。"）────────────
        # detect_page_state 对此返回 OK，需单独检测评论区组件错误
        if detect_reply_area_error(tab):
            reply_area_retry_hits += 1
            bump_metric(task_id, "reply_area_retries")
            logger.warning(
                f"  回复第 {page_num} 页检测到评论区加载错误，点击重试 "
                f"({reply_area_retry_hits}/{_REPLY_AREA_RETRY_SWITCH_THRESHOLD})..."
            )
            clicked = click_reply_retry_button(tab)
            if clicked:
                # 点击后重新等待数据包
                packet, _ = wait_for_target_packet(
                    tab,
                    timeout=compensation_probe_timeout(timeout),
                    accept_body=is_tweet_detail_body,
                )
                if packet:
                    _update_reply_rate_tracker(packet, task_id=task_id)
                    return packet
                logger.info(f"  评论区点击重试后仍无数据包（hit={reply_area_retry_hits}）")
            # 连续点击超过阈值，触发换账号信号
            if reply_area_retry_hits >= _REPLY_AREA_RETRY_SWITCH_THRESHOLD:
                logger.warning(
                    f"  评论区连续错误 {reply_area_retry_hits} 次，发出换账号信号"
                )
                if on_reply_area_error_switch_account:
                    try:
                        on_reply_area_error_switch_account()
                    except Exception as _cb_err:
                        logger.debug(f"换账号回调异常: {_cb_err}")
                raise SplashTimeoutSignal(
                    f"评论区持续加载错误 {reply_area_retry_hits} 次，尝试切换账号"
                )
            continue  # 继续下一次软重试

        state, reason = detect_page_state(tab)
        if state in {PageState.CHALLENGE, PageState.RATE_LIMITED, PageState.LOGIN_REQUIRED}:
            risk_hits += 1
            telemetry.record_event(
                task_id,
                "reply_risk_detected",
                status="running",
                phase=f"回复页检测到风险状态 {state.value}",
                page=page_num,
                risk_state=_to_risk_state(state),
                meta={"tweet_url": tweet_url, "hit": risk_hits},
            )
            # 首次就提醒用户在浏览器中完成验证
            if risk_hits == 1:
                promote_browser_for_manual_interaction(tab, reason=state.value)
            if risk_hits > policy.challenge_retry_times:
                promote_browser_for_manual_interaction(tab, reason=state.value)
                raise ChallengeSignal(
                    f"回复页检测到 {state.value} 且重试耗尽：{reason}",
                    risk_state=_to_risk_state(state),
                )
            logger.warning(
                f"  回复第 {page_num} 页风险状态 state={state.value}，"
                f"等待用户完成验证（{risk_hits}/{policy.challenge_retry_times}）"
            )
            wait_plan = build_challenge_wait_plan(
                tab,
                challenge_cooldown=policy.challenge_cooldown,
                cloudflare_wait_seconds=policy.cloudflare_wait_seconds,
            )
            if wait_plan.is_cloudflare:
                logger.info(
                    f"  回复第 {page_num} 页命中 Cloudflare 验证，等待 {wait_plan.seconds:.0f}s 供用户手动完成"
                )
            wait_for_challenge(wait_plan, task_id=task_id)
            # 冷却后重新检测（不刷新，等用户手动完成验证）
            recheck_state, _ = detect_page_state(tab)
            if recheck_state == PageState.OK:
                logger.info(f"  回复第 {page_num} 页用户已完成验证，页面恢复正常")
                continue

        if soft_attempt < policy.packet_soft_retries:
            bump_metric(task_id, "soft_retries")
            # 页面状态正常但无包：评论区可能已到底部，限制最多再重试1次
            if state == PageState.OK:
                if soft_attempt >= 1:
                    logger.debug(
                        f"  回复第 {page_num} 页页面正常但连续 {soft_attempt+1} 次无包，"
                        f"可能已到底部，提前退出软重试"
                    )
                    break
            continue

    # 翻页场景（page_num > 1）下跳过硬恢复：重新导航会丢失翻页 cursor，
    # 命中的是第 1 页数据（全重复），浪费时间且最终还要靠空页计数退出
    if page_num > 1:
        logger.debug(
            f"  回复第 {page_num} 页软重试耗尽，翻页场景跳过硬恢复（避免丢失 cursor）"
        )
        return None

    # 回复翻页场景下限制硬恢复次数为 1，避免无效等待
    # 评论区到底部时软重试超时属正常情况，不应再重新导航
    reply_hard_retries = min(1, policy.refresh_max_retries)
    for hard_attempt in range(reply_hard_retries):
        bump_metric(task_id, "hard_refreshes")
        wait = backoff_seconds(hard_attempt, base=2.0, cap=12.0)
        logger.warning(
            f"  回复第 {page_num} 页硬恢复刷新 {hard_attempt + 1}/{reply_hard_retries}，"
            f"退避 {wait:.1f}s"
        )
        sleep_with_jitter(wait, jitter_ratio=0.2, minimum=0.6)
        _safe_stop_listener(tab)
        tab.listen.start(TWEET_DETAIL_PATTERN)
        ok = navigate_with_retry(
            tab,
            tweet_url,
            max_retries=1,
            base_wait=2.5,
            post_load_wait=0.3,
            challenge_retry_times=policy.challenge_retry_times,
            challenge_cooldown=policy.challenge_cooldown,
            raise_on_risk=True,
            task_id=task_id,
        )
        if not ok:
            continue

        packet, _ = wait_for_target_packet(
            tab,
            timeout=compensation_probe_timeout(timeout),
            accept_body=is_tweet_detail_body,
        )
        if packet:
            _update_reply_rate_tracker(packet, task_id=task_id)
            return packet

    return None


def _update_reply_rate_tracker(packet, *, task_id: Optional[str] = None) -> None:
    """从 TweetDetail 数据包提取速率限制头并更新 tracker。"""
    result = extract_rate_headers(packet)
    if result:
        ep, remaining, limit, reset_ts = result
        get_tracker().update(ep, remaining, limit, reset_ts, task_id=task_id)


def _get_rate_limit_wait_sec(endpoint: str = "tweet_detail") -> float:
    """
    估算当前账号距限速重置的等待时间（秒）。
    从 rate_tracker 中读取最近一次响应头记录的 reset_ts。
    若无记录或已过期，返回保守估计 900s（15分钟）。
    """
    reset_ts = get_tracker().get_reset_ts(endpoint)
    if reset_ts > 0:
        wait = reset_ts - time.time()
        if 0 < wait < 1800:  # 合理范围：0~30 分钟
            return wait
    return 900.0  # 保守估计


def _pick_replacement_account(frozen_id: str, pool) -> "AccountEntry | None":
    """从池中选出一个不同于冻结账号的可用账号（round-robin 中第一个可用的）。"""
    return pool.pick_next_account(frozen_id)


def _inject_browser_instance_cookies_to_tab(tab, browser_instance) -> int:
    """将浏览器实例预设 Cookie 显式注入当前 tab。"""
    if browser_instance is None or not hasattr(browser_instance, "get_cookies"):
        return 0
    try:
        cookies = browser_instance.get_cookies()
    except Exception as e:
        logger.warning(f"读取浏览器实例待注入 Cookie 失败: {e}")
        return 0

    if not cookies:
        return 0

    injected = 0
    for cookie in cookies:
        name = cookie.get("name") if isinstance(cookie, dict) else None
        if not name:
            continue
        try:
            tab.set.cookies(_build_cookie_dict(cookie))
            injected += 1
        except Exception as e:
            logger.debug(f"补注入浏览器实例 Cookie {name} 失败: {e}")
    return injected


def _try_inject_pool_account_cookies(tab, task_id: Optional[str], browser_instance=None) -> bool:
    """
    尝试从账号池中获取任务绑定账号的 Cookie 并注入 tab。
    注入成功且登录验证通过时返回 True，否则返回 False。
    """
    if not task_id:
        return False
    try:
        from crawler.account_pool import get_pool
        from crawler.auth import ensure_login_with_pool_detailed
        import api.services.task_manager as _task_mgr
        from config import settings as _settings

        if not getattr(_settings, "account_pool_enabled", True):
            return False
        pool = get_pool()
        if pool.get_active_account_count() == 0:
            return False
        browser_bound_account_id = None
        if browser_instance is not None and hasattr(browser_instance, "get_bound_account"):
            browser_bound_account_id, _ = browser_instance.get_bound_account()
        bound_account_id, _ = _task_mgr.get_task_account(task_id)
        preferred_account_id = browser_bound_account_id or bound_account_id
        account = pool.get_account(preferred_account_id) if preferred_account_id else None
        if account is None and browser_instance is None:
            account = pool.pick_next_account()
        if account is None:
            return False
        result = ensure_login_with_pool_detailed(tab, account)
        if result.ok:
            logger.info(
                f"评论抓取前通过账号池账号 {account.alias!r} 恢复登录态成功"
            )
            return True
        logger.warning(f"评论抓取前账号池账号 {account.alias!r} 登录验证失败，reason={result.reason}")
    except Exception as e:
        logger.debug(f"评论抓取前尝试账号池注入失败: {e}")
    return False


def _ensure_reply_session_ready(tab, *, task_id: Optional[str], browser_instance=None) -> None:
    """抓评论前确保当前 tab 已处于可用登录态。

    浏览器池模式下，cookie 已通过 browser_instance.set_cookies() 预注入，
    new_tab() 创建时自动继承。直接跳过一切登录检测和 cookie 注入，零延迟。
    """
    # 浏览器池模式：cookie 已通过 new_tab() 自动继承，完全跳过
    if browser_instance is not None:
        _mark_login_cached(tab)
        return

    # TTL 内跳过重复检查
    if _is_login_cached(tab):
        return

    try:
        ensure_x_domain_context(tab)
    except Exception as e:
        logger.debug(f"评论抓取前建立 X 域上下文失败，将继续后续恢复: {e}")

    try:
        if check_login(tab):
            _mark_login_cached(tab)
            return
    except Exception as e:
        logger.debug(f"评论抓取前快速检查登录态失败，将走完整校验: {e}")

    injected = _inject_browser_instance_cookies_to_tab(tab, browser_instance)
    if injected:
        logger.info(f"评论抓取前补注入浏览器实例 Cookie {injected} 条")
        # 短暂等待让 cookie 生效（原先 0.5s → 0.15s，cookie 设置是同步操作）
        time.sleep(0.15)
        try:
            if check_login(tab):
                _mark_login_cached(tab)
                return
        except Exception:
            pass

    # 优先尝试通过账号池绑定账号恢复登录态（比默认 ensure_login_detailed 更精准）
    if _try_inject_pool_account_cookies(tab, task_id, browser_instance=browser_instance):
        _mark_login_cached(tab)
        return

    result = ensure_login_detailed(tab)
    if result.ok:
        _mark_login_cached(tab)
        return

    risk_state: RiskState = "challenge" if result.reason == "challenge_required" else "login_required"
    message = (
        f"评论抓取前未检测到可用 X 登录态（reason={result.reason}, "
        f"page_state={result.check.page_state}, url={result.check.current_url or '-'}"
        f"{', task_id=' + task_id if task_id else ''}）"
    )
    logger.warning(message)
    raise ChallengeSignal(message, risk_state=risk_state)


def fetch_replies(
    tweet_id: str,
    screen_name: str,
    reply_limit: int = 20,
    task_id: Optional[str] = None,
    timeout: Optional[float] = None,
    existing_tab=None,
    expected_count: int = 0,
    browser_instance=None,
) -> tuple[list[dict], dict | None]:
    """
    抓取指定推文的所有回复。

    Args:
        tweet_id:       目标推文 ID
        screen_name:    发推用户的 screen_name（构建 URL 用）
        reply_limit:    最多获取回复数量（0 表示不限制）
        task_id:        爬取任务 ID（用于原始响应存储路径 + 信号检查）
        timeout:        等待数据包超时（秒），默认使用全局配置
        existing_tab:   复用已有标签页（不传则新开）
        expected_count: 推文元数据中的评论数（reply_count），作为参考

    Returns:
        (replies, failure_info) 元组：
        - replies: 回复 tweet dict 列表
        - failure_info: 失败/不全信息 dict（None 表示成功）
    """
    if timeout is None:
        timeout = settings.crawler_timeout
    policy = RecoveryPolicy.from_settings(settings)

    tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
    all_replies: list[dict] = []
    seen_ids: set[str] = set()
    page_num = 0
    empty_page_count = 0  # 连续无新评论计数
    max_empty_pages = _dynamic_max_empty_pages(expected_count or 0)
    # 评论区换账号次数上限（防止无限换号）
    _reply_account_switches = 0
    _REPLY_MAX_ACCOUNT_SWITCHES = 2

    # 决定是否使用外部传入的 tab（DFS 时复用避免频繁开关）
    if existing_tab is not None:
        tab = existing_tab
    elif browser_instance is not None:
        tab = browser_instance.new_tab()
    else:
        tab = get_new_tab()
    should_close = (existing_tab is None)

    # 日志中展示预期评论数以便对比
    expected_info = f"，预期约 {expected_count} 条" if expected_count else ""

    try:
        _ensure_reply_session_ready(tab, task_id=task_id, browser_instance=browser_instance)
        tab.listen.start(TWEET_DETAIL_PATTERN)
        logger.info(f"开始抓取回复: tweet_id={tweet_id}, url={tweet_url}{expected_info}")
        telemetry.record_event(
            task_id,
            "reply_fetch_started",
            status="running",
            phase=f"开始抓取回复 tweet_id={tweet_id}",
            meta={"tweet_id": tweet_id, "screen_name": screen_name, "expected_count": expected_count},
        )

        # 导航到推文详情页（含错误页自动刷新）
        ok = navigate_with_retry(
            tab,
            tweet_url,
            max_retries=policy.refresh_max_retries,
            base_wait=1.0,
            load_timeout=12.0,
            post_load_wait=0.0,
            challenge_retry_times=policy.challenge_retry_times,
            challenge_cooldown=policy.challenge_cooldown,
            raise_on_risk=True,
            task_id=task_id,
        )
        # 初始导航失败（全页 "Something went wrong"）→ 先换账号重试，而非直接放弃
        if not ok and _reply_account_switches < _REPLY_MAX_ACCOUNT_SWITCHES:
            switched = _try_inject_pool_account_cookies(tab, task_id, browser_instance=browser_instance)
            if switched:
                _reply_account_switches += 1
                _invalidate_login_cache(tab)
                bump_metric(task_id, "navigate_error_account_switches")
                logger.info(
                    f"推文详情页初始导航失败，已切换账号（第 {_reply_account_switches} 次），"
                    f"重新尝试 tweet_id={tweet_id}"
                )
                _safe_stop_listener(tab)
                tab.listen.start(TWEET_DETAIL_PATTERN)
                ok = navigate_with_retry(
                    tab,
                    tweet_url,
                    max_retries=2,
                    base_wait=2.0,
                    load_timeout=15.0,
                    challenge_retry_times=policy.challenge_retry_times,
                    challenge_cooldown=policy.challenge_cooldown,
                    raise_on_risk=True,
                    task_id=task_id,
                )
        if not ok:
            logger.error(f"推文详情页反复出现错误，跳过 tweet_id={tweet_id}")
            failure = {
                "tweet_id": tweet_id,
                "screen_name": screen_name,
                "expected_count": expected_count,
                "fetched_count": 0,
                "error_reason": "推文详情页反复加载失败（已尝试切换账号）",
            }
            return [], failure

        # 导航完成后立即执行一次渐进式滚动，触发 TweetDetail API 初始加载。
        # X 评论区由滚动触发数据包，第一页同样需要滚动才能稳定拿到包，
        # 不滚动直接等会浪费 quick_probe_timeout 秒的无效等待。
        _scroll_incremental(tab, task_id=task_id)

        while True:
            # 每页检查控制信号
            check_signal(task_id)

            page_num += 1
            logger.info(f"  等待回复第 {page_num} 页数据包（tweet_id={tweet_id}）...")
            telemetry.record_event(
                task_id,
                "reply_wait_packet",
                status="running",
                phase=f"等待回复第 {page_num} 页数据包",
                page=page_num,
                meta={"tweet_id": tweet_id},
            )
            try:
                packet = _wait_reply_packet_with_recovery(
                    tab=tab,
                    timeout=timeout,
                    page_num=page_num,
                    tweet_url=tweet_url,
                    task_id=task_id,
                    policy=policy,
                )
            except SplashTimeoutSignal as splash_err:
                # 评论区持续加载错误，尝试换账号后重新导航
                logger.warning(f"  {splash_err}")
                bump_metric(task_id, "reply_area_account_switches")
                _reply_account_switches += 1
                switched = False
                if _reply_account_switches <= _REPLY_MAX_ACCOUNT_SWITCHES:
                    switched = _try_inject_pool_account_cookies(tab, task_id, browser_instance=browser_instance)
                    if switched:
                        _invalidate_login_cache(tab)
                        logger.info(f"  评论区换账号成功（第 {_reply_account_switches} 次），重新导航")
                        _safe_stop_listener(tab)
                        tab.listen.start(TWEET_DETAIL_PATTERN)
                        navigate_with_retry(
                            tab, tweet_url,
                            max_retries=policy.refresh_max_retries,
                            base_wait=3.0, load_timeout=15.0,
                            challenge_retry_times=policy.challenge_retry_times,
                            challenge_cooldown=policy.challenge_cooldown,
                            task_id=task_id,
                        )
                        _scroll_incremental(tab, task_id=task_id)
                        continue  # 继续采集
                if not switched:
                    logger.warning(
                        f"  评论区错误持续且无可用备用账号，跳过 tweet_id={tweet_id}"
                    )
                    break  # 放弃本推文评论采集

            if not packet:
                # 所有重试均失败，停止当前推文评论抓取
                logger.warning(f"  回复第 {page_num} 页连续超时（tweet_id={tweet_id}），停止抓取")
                telemetry.record_event(
                    task_id,
                    "reply_packet_timeout_stop",
                    status="running",
                    phase=f"回复第 {page_num} 页连续超时，停止当前推文回复抓取",
                    page=page_num,
                    meta={"tweet_id": tweet_id},
                )
                break

            try:
                body = extract_packet_body_dict(packet)
                if not isinstance(body, dict):
                    logger.debug(f"  非 JSON 响应，跳过（url={packet.url[:80]}）")
                    continue

                # 持久化原始响应
                if task_id:
                    save_reply_response(task_id, tweet_id, page_num, body)

                _, page_replies, bottom_cursor, _, has_spam_boundary = parse_tweet_detail_response(
                    body, focal_tweet_id=tweet_id
                )

                # 去重
                new_replies = [r for r in page_replies if r.get("id") not in seen_ids]
                for r in new_replies:
                    seen_ids.add(r.get("id", ""))
                all_replies.extend(new_replies)

                logger.info(
                    f"  回复第 {page_num} 页：{len(page_replies)} 条"
                    f"（新增 {len(new_replies)} 条），"
                    f"累计 {len(all_replies)} 条"
                    f"{'/' + str(expected_count) if expected_count else ''}"
                    f"（tweet_id={tweet_id}）"
                )
                telemetry.record_event(
                    task_id,
                    "reply_page_parsed",
                    status="running",
                    phase=f"回复第 {page_num} 页解析完成",
                    page=page_num,
                    delta_replies=len(new_replies),
                    meta={"tweet_id": tweet_id, "total_replies": len(all_replies)},
                )

                # 更新连续空页计数
                if len(new_replies) == 0:
                    empty_page_count += 1
                    # 低评论推文快速放弃：预期 ≤3 条但首页就没数据，不值得重试
                    if expected_count > 0 and expected_count <= 3 and page_num == 1:
                        logger.info(
                            f"  低评论推文首页无数据（预期 {expected_count} 条），直接跳过"
                        )
                        break
                    # X 评论区翻页时出现重复/空页是常见现象（cursor 漂移等），
                    # 不应过于激进地放弃——使用 _dynamic_max_empty_pages 的完整阈值
                    bump_metric(task_id, "empty_pages")
                    if empty_page_count >= max_empty_pages:
                        logger.info(
                            f"  连续 {empty_page_count} 页无新评论"
                            f"{'（已有 ' + str(len(all_replies)) + ' 条，提前结束）' if len(all_replies) > 0 else ''}"
                            f"，停止翻页"
                        )
                        break
                else:
                    empty_page_count = 0  # 有新数据则重置计数

                # ── 垃圾信息边界检测：出现"显示可能的垃圾信息"时停止翻页 ──
                if has_spam_boundary:
                    logger.info(
                        f"  检测到垃圾信息边界（ShowMoreThreads），"
                        f"有效评论已加载完毕，停止翻页（已抓 {len(all_replies)} 条）"
                    )
                    telemetry.record_event(
                        task_id,
                        "reply_spam_boundary",
                        status="running",
                        phase="检测到垃圾信息边界，停止翻页",
                        page=page_num,
                        meta={"tweet_id": tweet_id, "fetched": len(all_replies)},
                    )
                    break

                # ── 快速退出：评论数已达标时立即完成 ────────
                if expected_count > 0:
                    # 条件1：已获取评论数已达到或超过预期数量
                    if len(all_replies) >= expected_count:
                        logger.info(
                            f"  ✅ 快速完成：已获取 {len(all_replies)} 条评论"
                            f"（预期 {expected_count} 条），无需翻页"
                        )
                        telemetry.record_event(
                            task_id,
                            "reply_quick_complete",
                            status="running",
                            phase="回复已达到预期，快速完成",
                            page=page_num,
                            meta={"tweet_id": tweet_id, "fetched": len(all_replies), "expected": expected_count},
                        )
                        break
                    # 条件2：API 无分页游标 + 覆盖率 ≥ 80%（reply_count 可能不完全准确）
                    if not bottom_cursor and len(all_replies) >= expected_count * 0.8:
                        pct = len(all_replies) / expected_count * 100
                        logger.info(
                            f"  ✅ 快速完成：无更多分页且已达 {len(all_replies)}/{expected_count} "
                            f"条（覆盖率 {pct:.0f}%），跳过翻页"
                        )
                        telemetry.record_event(
                            task_id,
                            "reply_quick_complete",
                            status="running",
                            phase="回复覆盖率达标且无更多分页，快速完成",
                            page=page_num,
                            meta={"tweet_id": tweet_id, "fetched": len(all_replies), "expected": expected_count},
                        )
                        break


                if reply_limit and len(all_replies) >= reply_limit:
                    all_replies = all_replies[:reply_limit]
                    logger.info(f"  已达回复上限 {reply_limit} 条，停止")
                    break

                # 无更多评论（API 没有返回 bottom_cursor）
                if not bottom_cursor:
                    # API 无 cursor 说明评论区已到底，无论覆盖率如何直接停止
                    # 之前尝试额外滚动的逻辑会导致反复等包超时，浪费 20-30s
                    logger.info(f"  评论区无更多数据（tweet_id={tweet_id}，已抓 {len(all_replies)} 条）")
                    break

                # ── 翻页操作：渐进式滚动触发懒加载 ──────────────────────
                before_scroll_wait(task_id=task_id)

                # 渐进式滚动到底部，触发 TweetDetail API 加载更多评论
                logger.debug(f"  执行渐进式滚动加载下一页评论...")
                _scroll_incremental(tab, task_id=task_id)

            except ChallengeSignal:
                raise
            except Exception as e:
                logger.error(f"  回复第 {page_num} 页解析失败: {e}", exc_info=True)
                break

    finally:
        _safe_stop_listener(tab)
        if should_close:
            try:
                tab.close()
            except Exception:
                pass

    # 输出抓取结果摘要
    coverage = ""
    if expected_count:
        pct = round(len(all_replies) / expected_count * 100) if expected_count else 0
        coverage = f"（覆盖率 {pct}%，预期 {expected_count} 条）"
    logger.info(f"回复抓取完成: tweet_id={tweet_id}，共 {len(all_replies)} 条{coverage}")
    telemetry.record_event(
        task_id,
        "reply_fetch_finished",
        status="running",
        phase=f"回复抓取完成 tweet_id={tweet_id}",
        delta_replies=len(all_replies),
        meta={"tweet_id": tweet_id, "coverage": coverage},
    )

    # 判定是否需要记录为失败/不全
    failure_info = None
    if expected_count and expected_count > 0:
        pct = len(all_replies) / expected_count * 100 if expected_count else 100
        if pct < 50 and expected_count >= 3:
            failure_info = {
                "tweet_id": tweet_id,
                "screen_name": screen_name,
                "expected_count": expected_count,
                "fetched_count": len(all_replies),
                "error_reason": f"覆盖率不足 ({pct:.0f}%)，预期 {expected_count} 条仅抓到 {len(all_replies)} 条",
            }
    if len(all_replies) == 0 and expected_count and expected_count > 0:
        if not failure_info:
            failure_info = {
                "tweet_id": tweet_id,
                "screen_name": screen_name,
                "expected_count": expected_count,
                "fetched_count": 0,
                "error_reason": "未抓取到任何评论",
            }

    return all_replies, failure_info


def fetch_replies_batch(
    tweets: list[dict],
    max_replies_per_tweet: int = 20,
    task_id: Optional[str] = None,
    timeout: Optional[float] = None,
    progress_callback=None,
    strategy: str = "dfs",
    reply_depth: int = 2,
    browser_instance=None,
) -> tuple[list[dict], list[dict]]:
    """
    批量抓取多条推文的回复（统一 DFS 模式，搜到即抓）。
    每条推文开独立标签页抓取，顺序执行。
    支持跨任务去重：互动指标未变化的推文直接复用缓存评论。

    当收到 StopSignal 时，会将已抓取回复的推文 + 剩余未处理推文合并后
    通过 StopSignal.partial_tweets 携带，确保已抓取的回复数据不丢失。

    Args:
        tweets:                推文 dict 列表（需含 id 和 author.screen_name）
        max_replies_per_tweet: 每条推文最多抓取的回复数量
        task_id:               任务 ID
        timeout:               超时
        progress_callback:     每条推文完成后调用 callback(tweet_id, replies)

    Returns:
        (updated_tweets, failed_records) 元组
    """
    import api.services.task_manager as _task_mgr
    from config import settings as _settings
    from crawler.tweet_dedup import check_dedup, register_tweets

    tag = strategy.upper()
    dedup_enabled = _settings.crawler_dedup_enabled
    dedup_hit_count = 0
    updated_tweets = []
    failed_records: list[dict] = []

    _shared_reply_tab = None
    _owns_shared_tab = False

    def _ensure_shared_reply_tab():
        nonlocal _shared_reply_tab, _owns_shared_tab
        if _shared_reply_tab is not None:
            return _shared_reply_tab
        if browser_instance is not None:
            _shared_reply_tab = browser_instance.new_tab()
            _owns_shared_tab = True
        elif reply_depth <= 1:
            # 非嵌套模式：batch 内共享同一个 tab
            _shared_reply_tab = get_new_tab()
            _owns_shared_tab = True
        return _shared_reply_tab

    for i, tweet in enumerate(tweets):
        # 每条推文前检查信号
        try:
            check_signal(task_id)
        except StopSignal as e:
            merge_remaining(updated_tweets, tweets, i)
            raise StopSignal(str(e), partial_tweets=updated_tweets)

        tweet_id = tweet.get("id", "")
        screen_name = (tweet.get("author") or {}).get("screen_name", "")
        # 从推文元数据获取预期评论数
        expected_count = (tweet.get("metrics") or {}).get("replies", 0)

        if not tweet_id or not screen_name:
            logger.warning(f"推文缺少 id 或 screen_name，跳过回复抓取（index={i}）")
            updated_tweets.append(tweet)
            continue

        # 跳过已有回复数据的推文（断点恢复时避免重复抓取）
        existing_replies = tweet.get("replies")
        if existing_replies is not None:
            logger.info(
                f"[{tag}] 跳过 tweet_id={tweet_id}（已有 {len(existing_replies)} 条回复），"
                f"无需重复抓取"
            )
            updated_tweets.append(tweet)
            if progress_callback:
                try:
                    progress_callback(tweet_id, existing_replies)
                except Exception:
                    pass
            continue

        # 跳过 0 评论的帖子，无需打开详情页
        if expected_count == 0:
            logger.info(
                f"[{tag}] 跳过 tweet_id={tweet_id}（0 条评论），无需抓取回复"
            )
            tweet = dict(tweet)
            tweet["replies"] = []
            updated_tweets.append(tweet)
            if progress_callback:
                try:
                    progress_callback(tweet_id, [])
                except Exception:
                    pass
            continue

        # ── 跨任务去重检查（缓存命中跳过评论抓取） ─────────────
        if dedup_enabled:
            hit, cached_replies = check_dedup(tweet)
            if hit and cached_replies is not None:
                dedup_hit_count += 1
                tweet = dict(tweet)
                tweet["replies"] = cached_replies
                updated_tweets.append(tweet)
                logger.info(
                    f"[{tag}] 去重命中 tweet_id={tweet_id}，"
                    f"复用 {len(cached_replies)} 条缓存评论"
                )
                telemetry.record_event(
                    task_id,
                    "reply_dedup_hit",
                    status="running",
                    phase=f"[{tag}] 推文命中去重缓存",
                    delta_replies=len(cached_replies),
                    meta={"tweet_id": tweet_id},
                )
                if progress_callback:
                    try:
                        progress_callback(tweet_id, cached_replies)
                    except Exception:
                        pass
                continue

        # 更新阶段提示（告知用户正在抓第几条推文的回复）
        if task_id:
            _task_mgr.update_task_phase(
                task_id,
                f"[{tag}] 正在抓取第 {i + 1}/{len(tweets)} 条推文的回复 "
                f"(@{screen_name}，预期 {expected_count} 条)..."
            )

        logger.info(
            f"[{tag}] 抓取回复进度 {i+1}/{len(tweets)}: "
            f"tweet_id={tweet_id}，预期评论 {expected_count} 条"
        )
        # 当需要抓二级评论时，手动开标签页让一级评论页面保持打开
        # 模拟人类行为：打开推文→看评论→点击评论看子评论→全看完再关闭
        need_nested = (reply_depth > 1)
        if need_nested:
            reply_tab = browser_instance.new_tab() if browser_instance is not None else get_new_tab()
        else:
            reply_tab = _ensure_shared_reply_tab()

        try:
            replies, failure_info = fetch_replies(
                tweet_id=tweet_id,
                screen_name=screen_name,
                reply_limit=max_replies_per_tweet,
                task_id=task_id,
                timeout=timeout,
                expected_count=expected_count,
                existing_tab=reply_tab,  # 传入外部 tab，fetch_replies 不会关闭它
                browser_instance=browser_instance,
            )
            tweet = dict(tweet)  # 浅拷贝，防止污染原对象
            tweet["replies"] = replies
            if failure_info:
                failure_info["task_id"] = task_id or ""
                failed_records.append(failure_info)

            # ── 二级评论递归抓取（一级评论标签页保持打开） ─────────
            if replies and need_nested:
                from crawler.nested_reply_fetcher import fetch_nested_replies
                try:
                    tweet["replies"], nested_failed = fetch_nested_replies(
                        replies,
                        current_depth=1,
                        max_depth=reply_depth,
                        max_replies_per_tweet=max_replies_per_tweet,
                        task_id=task_id,
                        timeout=timeout,
                        browser_instance=browser_instance,
                    )
                    failed_records.extend(nested_failed)
                except StopSignal as e:
                    updated_tweets.append(tweet)
                    merge_remaining(updated_tweets, tweets, i + 1)
                    raise StopSignal(str(e), partial_tweets=updated_tweets)
                except ChallengeSignal:
                    raise
                except Exception as e:
                    logger.error(f"拓展抓取 tweet_id={tweet_id} 的子评论失败: {e}", exc_info=True)
        except StopSignal as e:
            # 当前推文的回复抓取被中断，标记空回复后携带已处理数据抛出
            tweet = dict(tweet)
            tweet["replies"] = []
            updated_tweets.append(tweet)
            merge_remaining(updated_tweets, tweets, i + 1)
            raise StopSignal(str(e), partial_tweets=updated_tweets)
        except ChallengeSignal:
            _invalidate_login_cache(reply_tab)
            raise
        except Exception as e:
            import traceback
            error_msg = str(e).lower()
            if "disconnected" in error_msg or "connection lost" in error_msg or "target closed" in error_msg:
                logger.warning(f"检测到浏览器断开连接，尝试恢复浏览器: {e}")
                _invalidate_login_cache(reply_tab)
                from crawler.browser import ensure_browser_alive
                ensure_browser_alive()
            logger.error(f"抓取 tweet_id={tweet_id} 回复失败: {e}", exc_info=True)
            tweet = dict(tweet)
            tweet["replies"] = []
            failed_records.append({
                "task_id": task_id or "",
                "tweet_id": tweet_id,
                "screen_name": screen_name,
                "expected_count": expected_count,
                "fetched_count": 0,
                "error_reason": f"异常: {str(e)[:200]}",
            })
        finally:
            # 二级评论全部抓完后，关闭一级评论标签页（仅嵌套模式独立 tab）
            if reply_tab and need_nested:
                try:
                    reply_tab.close()
                except Exception:
                    pass

        updated_tweets.append(tweet)

        if progress_callback:
            try:
                progress_callback(tweet_id, tweet.get("replies", []))
            except Exception:
                pass

        # 礼貌性间隔：基于 tweet_detail 动态间隔，多账号时自动缩短
        # 页面导航+加载本身已占 3-5s，仅需补足最小安全间隔差值
        from crawler.account_pool import compute_dynamic_interval
        _rate_mult_reply = get_tracker().get_sleep_multiplier("tweet_detail", task_id=task_id)
        _min_r, _max_r, _ = compute_dynamic_interval("tweet_detail")
        _nav_latency_compensation = 10.0  # 导航+页面加载+包等待实际消耗
        _target_interval = random.uniform(_min_r, _max_r) * _rate_mult_reply
        _actual_sleep = max(0.2, _target_interval - _nav_latency_compensation)
        interruptible_sleep(_actual_sleep, task_id=task_id)

    # ── 清理 batch 级共享 tab ──────────────────────────────────────
    if _owns_shared_tab and _shared_reply_tab:
        try:
            _shared_reply_tab.close()
        except Exception:
            pass

    # ── 批次完成后注册指纹（供后续任务去重复用） ──────────────────
    if dedup_enabled and task_id:
        register_tweets(updated_tweets, task_id)
        if dedup_hit_count:
            logger.info(
                f"[{tag}] 本批去重统计: {dedup_hit_count}/{len(tweets)} 条推文命中缓存"
            )

    return updated_tweets, failed_records


# ═══════════════════════════════════════════════════════════════════
#  单条推文回复抓取（供 pipeline.CrawlPipeline reply_worker 调用）
# ═══════════════════════════════════════════════════════════════════

def fetch_replies_single(
    tweet: dict,
    *,
    task_id: Optional[str] = None,
    timeout: Optional[float] = None,
    max_replies_per_tweet: int = 20,
    reply_depth: int = 2,
    existing_tab=None,
    browser_instance=None,
) -> tuple[dict, dict | None]:
    """
    对单条推文抓取回复，返回 (updated_tweet, failure_info)。

    供 crawler.pipeline.CrawlPipeline 的 reply_worker 逐条调用。
    与 fetch_replies_batch 的区别：仅处理一条推文，不管理 tab 生命周期，
    由调用方（pipeline）提供并复用 reply_tab。

    Args:
        tweet:                 推文 dict（需含 id 和 author.screen_name）
        task_id:               任务 ID
        timeout:               超时（秒）
        max_replies_per_tweet: 最多抓取的回复数
        reply_depth:           回复层级深度（>1 抓二级评论）
        existing_tab:          复用的已有标签页（不传则新开）
        browser_instance:      浏览器池实例

    Returns:
        (updated_tweet, failure_info)
        - updated_tweet: 附有 replies 字段的推文 dict
        - failure_info:  失败 dict 或 None
    """
    from config import settings as _settings

    tweet_id = str(tweet.get("id", ""))
    screen_name = (tweet.get("author") or {}).get("screen_name", "")
    expected_count = (tweet.get("metrics") or {}).get("replies", 0)

    # 已有回复数据，直接返回（断点续爬时跳过）
    if tweet.get("replies") is not None:
        return tweet, None

    # 0 评论，无需打开详情页
    if expected_count == 0:
        updated = dict(tweet)
        updated["replies"] = []
        return updated, None

    if timeout is None:
        timeout = _settings.crawler_timeout

    # ── 跨任务去重检查（与 fetch_replies_batch 保持一致） ──
    dedup_enabled = getattr(_settings, "crawler_dedup_enabled", True)
    if dedup_enabled:
        from crawler.tweet_dedup import check_dedup
        hit, cached_replies = check_dedup(tweet)
        if hit and cached_replies is not None:
            updated = dict(tweet)
            updated["replies"] = cached_replies
            logger.info(
                f"[Pipeline] 去重命中 tweet_id={tweet_id}，"
                f"复用 {len(cached_replies)} 条缓存评论"
            )
            return updated, None

    if not tweet_id or not screen_name:
        logger.warning(f"[Pipeline] 推文缺少 id 或 screen_name，跳过 tweet_id={tweet_id}")
        updated = dict(tweet)
        updated["replies"] = []
        return updated, None

    try:
        replies, failure_info = fetch_replies(
            tweet_id=tweet_id,
            screen_name=screen_name,
            reply_limit=max_replies_per_tweet,
            task_id=task_id,
            timeout=timeout,
            existing_tab=existing_tab,
            expected_count=expected_count,
            browser_instance=browser_instance,
        )
    except Exception as e:
        # 非致命异常：记录失败，返回空回复
        from crawler.crawl_signals import StopSignal, ChallengeSignal
        if isinstance(e, (StopSignal, ChallengeSignal)):
            raise
        logger.error(f"[Pipeline] fetch_replies_single: tweet_id={tweet_id} 失败: {e}", exc_info=True)
        updated = dict(tweet)
        updated["replies"] = []
        failure_info = {
            "task_id": task_id or "",
            "tweet_id": tweet_id,
            "screen_name": screen_name,
            "expected_count": expected_count,
            "fetched_count": 0,
            "error_reason": f"pipeline 异常: {str(e)[:200]}",
        }
        return updated, failure_info

    # ── 二级评论递归抓取 ──────────────────────────────────────
    need_nested = (reply_depth > 1)
    updated = dict(tweet)
    updated["replies"] = replies

    if replies and need_nested:
        from crawler.nested_reply_fetcher import fetch_nested_replies
        try:
            updated["replies"], nested_failed = fetch_nested_replies(
                replies,
                current_depth=1,
                max_depth=reply_depth,
                max_replies_per_tweet=max_replies_per_tweet,
                task_id=task_id,
                timeout=timeout,
                browser_instance=browser_instance,
            )
        except Exception as nested_e:
            from crawler.crawl_signals import StopSignal, ChallengeSignal
            if isinstance(nested_e, (StopSignal, ChallengeSignal)):
                raise
            logger.error(f"[Pipeline] 二级评论抓取失败 tweet_id={tweet_id}: {nested_e}", exc_info=True)
        else:
            # nested_failed 合并到 failure_info 之外（调用方通过 pipeline.failed_records 收集）
            if failure_info is None and nested_failed:
                pass  # nested_failed 由调用者通过 on_reply_done 机制统计

    if failure_info:
        failure_info["task_id"] = task_id or ""

    return updated, failure_info
