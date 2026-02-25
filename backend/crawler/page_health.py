"""
页面健康检测工具

检测 X/Twitter 页面状态并执行恢复策略。
"""
import time
import logging
from typing import Optional

from crawler.crawl_signals import ChallengeSignal, RiskState
from crawler.page_state import PageState, detect_page_state, is_error_like_state
from crawler.recovery_policy import sleep_with_jitter, backoff_seconds

logger = logging.getLogger(__name__)


def _to_risk_state(state: PageState) -> RiskState:
    if state == PageState.RATE_LIMITED:
        return "rate_limited"
    if state == PageState.LOGIN_REQUIRED:
        return "login_required"
    return "challenge"


def is_error_page(tab) -> bool:
    """兼容旧调用：仅将 transient_error / rate_limited 判定为错误页。"""
    state, _ = detect_page_state(tab)
    return is_error_like_state(state)


def navigate_with_retry(
    tab,
    url: str,
    *,
    max_retries: int = 3,
    base_wait: float = 3.0,
    load_timeout: float = 30.0,
    post_load_wait: float = 0.0,
    challenge_retry_times: int = 2,
    challenge_cooldown: float = 8.0,
    raise_on_risk: bool = False,
    task_id: Optional[str] = None,
) -> bool:
    """
    导航到目标 URL，遇到错误页面自动刷新重试。

    Args:
        tab:            DrissionPage 标签页对象
        url:            目标 URL
        max_retries:    最大重试次数（不含首次）
        base_wait:      每次重试前的等待时间（秒），每次翻倍
        load_timeout:   页面加载超时（秒）
        post_load_wait: 加载成功后额外等待时间（秒，0 表示不额外等待）
        task_id:        任务 ID（仅用于日志标记）

    Returns:
        True  = 页面加载正常
        False = 所有重试失败
    """
    log_prefix = f"[task={task_id}] " if task_id else ""

    challenge_hits = 0

    for attempt in range(max_retries + 1):
        try:
            if attempt == 0:
                tab.get(url, timeout=load_timeout)
            else:
                wait = backoff_seconds(attempt - 1, base=base_wait)
                logger.warning(
                    f"{log_prefix}检测到错误页面，{wait:.1f}s 后第 {attempt} 次刷新重试... (url={url[:80]})"
                )
                sleep_with_jitter(wait)
                tab.refresh()
                # 等待刷新后页面加载
                time.sleep(1.6)

            state, reason = detect_page_state(tab)
            if state == PageState.OK:
                if post_load_wait > 0:
                    time.sleep(post_load_wait)
                if attempt > 0:
                    logger.info(f"{log_prefix}第 {attempt} 次刷新后页面恢复正常")
                return True

            if state in {PageState.CHALLENGE, PageState.RATE_LIMITED, PageState.LOGIN_REQUIRED}:
                challenge_hits += 1
                logger.warning(
                    f"{log_prefix}检测到风险页 state={state.value}, reason={reason}, "
                    f"hit={challenge_hits}/{challenge_retry_times}"
                )
                if challenge_hits <= challenge_retry_times:
                    sleep_with_jitter(challenge_cooldown, jitter_ratio=0.1, minimum=0.8)
                    continue
                if raise_on_risk:
                    raise ChallengeSignal(
                        f"检测到 {state.value}，请人工处理后继续",
                        risk_state=_to_risk_state(state),
                    )
                if attempt == max_retries:
                    logger.error(f"{log_prefix}风险页面持续存在，放弃 (url={url[:80]})")
                    return False
                continue

            if is_error_like_state(state):
                if attempt == max_retries:
                    logger.error(f"{log_prefix}已达最大重试次数 {max_retries}，放弃 (url={url[:80]})")
                    return False
                continue  # 继续重试

            # 兜底：未知状态视为可继续
            if post_load_wait > 0:
                time.sleep(post_load_wait)
            return True

        except ChallengeSignal:
            raise
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"{log_prefix}导航失败，已达最大重试次数: {e}")
                return False
            logger.warning(f"{log_prefix}导航异常 (attempt={attempt}): {e}")
            sleep_with_jitter(base_wait)

    return False
