"""
页面健康检测工具

检测 X/Twitter 页面状态并执行恢复策略。
"""
import os
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from crawler.crawl_signals import ChallengeSignal, RiskState
from crawler.browser import promote_browser_for_manual_interaction
from crawler.page_state import PageState, detect_page_state, is_error_like_state
from crawler.recovery_policy import sleep_with_jitter, backoff_seconds
from crawler.runtime_metrics import bump_metric
from crawler.utils import interruptible_sleep
from crawler import telemetry

logger = logging.getLogger(__name__)

# 调试快照保存目录
_DEBUG_DIR = Path(__file__).resolve().parent.parent / "logs" / "debug"

# ── 连续错误自适应冷却 ────────────────────────────────────────────
# 追踪跨导航的连续 transient_error 次数，当错误密集出现时自动升级等待时间
import threading

_consecutive_errors = 0
_error_lock = threading.Lock()

# 连续错误次数 → 额外冷却秒数（递增缓冲，给 X 服务端恢复时间）
_COOLDOWN_TIERS = [
    (3, 8.0),    # 连续 3 次错误后额外等 8 秒
    (5, 15.0),   # 连续 5 次后等 15 秒
    (8, 30.0),   # 连续 8 次后等 30 秒
    (12, 60.0),  # 连续 12 次后等 60 秒
]


def _record_error() -> float:
    """记录一次错误，返回当前应追加的冷却时间（秒）。"""
    global _consecutive_errors
    with _error_lock:
        _consecutive_errors += 1
        count = _consecutive_errors
    extra = 0.0
    for threshold, cooldown in _COOLDOWN_TIERS:
        if count >= threshold:
            extra = cooldown
    if extra > 0:
        logger.info(f"连续错误页累计 {count} 次，追加冷却 {extra:.0f}s")
    return extra


def _record_success() -> None:
    """页面加载成功，重置连续错误计数。"""
    global _consecutive_errors
    with _error_lock:
        if _consecutive_errors > 0:
            logger.debug(f"页面恢复正常，重置连续错误计数（之前 {_consecutive_errors} 次）")
            _consecutive_errors = 0


def _save_debug_snapshot(tab, state: PageState, reason: str, attempt: int, task_id: Optional[str] = None) -> None:
    """
    保存当前页面的截图和 HTML，方便在无显示器的 Linux 服务器上诊断页面问题。
    文件保存到 backend/logs/debug/ 目录。
    """
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = task_id[:8] if task_id else "notask"
        prefix = f"{ts}_{tag}_attempt{attempt}_{state.value}"

        # 保存截图
        try:
            screenshot_name = f"{prefix}.png"
            saved_path = tab.get_screenshot(path=str(_DEBUG_DIR), name=screenshot_name, full_page=True)
            logger.info(f"已保存调试截图: {saved_path}")

            # 把截图 URL 同步到任务状态里，让前端可见
            if task_id:
                try:
                    from api.services import task_manager
                    if task_manager.get_task_summary(task_id) is not None:
                        task_manager.update_task_debug_screenshot(
                            task_id,
                            f"/api/v1/debug/{screenshot_name}",
                        )
                        task_manager.send_signal(task_id, "changed")
                except Exception as e:
                    logger.warning(f"无法将截图 URL 同步至任务状态: {e}")

        except Exception as e:
            logger.warning(f"保存截图失败: {e}")

        # 保存 HTML
        try:
            html_path = _DEBUG_DIR / f"{prefix}.html"
            html_content = tab.html or "(empty)"
            html_path.write_text(html_content, encoding="utf-8")
            logger.info(f"已保存页面 HTML: {html_path}")
        except Exception as e:
            logger.warning(f"保存 HTML 失败: {e}")

        # 保存 URL 和状态信息
        try:
            info_path = _DEBUG_DIR / f"{prefix}_info.txt"
            info = (
                f"时间: {datetime.now().isoformat()}\n"
                f"URL: {tab.url}\n"
                f"页面状态: {state.value}\n"
                f"原因: {reason}\n"
                f"重试次数: {attempt}\n"
                f"Task ID: {task_id}\n"
            )
            info_path.write_text(info, encoding="utf-8")
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"保存调试快照失败（不影响正常流程）: {e}")


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
                interruptible_sleep(1.6, task_id=task_id)

            state, reason = detect_page_state(tab)

            # ── 二次验证：过滤 noscript 误判 ──────────────────────────
            # X 的 HTML 始终包含 <noscript>JavaScript is not available.</noscript>
            # 如果 detect_page_state 将其误判为 transient_error，这里兜底修正
            # 注意：JS 未执行空壳页不是误判，必须跳过修正
            if state == PageState.TRANSIENT_ERROR and "JS 未执行" not in reason:
                try:
                    import re as _re
                    _raw = tab.html or ""
                    # 去掉 noscript 块
                    _cleaned = _re.sub(r"(?is)<noscript\b[^>]*>.*?</noscript>", "", _raw)
                    _cleaned = _re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", _cleaned)
                    _cleaned = _re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", _cleaned)
                    _vis = _re.sub(r"(?is)<[^>]+>", " ", _cleaned)
                    _vis = _re.sub(r"\s+", " ", _vis).strip().lower()
                    _vis = _vis.replace("javascript is not available", "")
                    _real_markers = [
                        "something went wrong", "try reloading",
                        "hmm...this page doesn", "hmm, this page doesn",
                        "发生错误", "出错了",
                    ]
                    if not any(m in _vis for m in _real_markers):
                        logger.info(
                            f"{log_prefix}transient_error 疑似误判（noscript 残留），"
                            f"已修正为 OK"
                        )
                        state = PageState.OK
                        reason = "二次验证修正：noscript 误判"
                except Exception:
                    pass  # 二次验证失败不影响主流程

            # 非 OK 状态时保存调试快照（仅首次和末次尝试，避免过多文件）
            if state != PageState.OK and (attempt == 0 or attempt == max_retries):
                _save_debug_snapshot(tab, state, reason, attempt, task_id)

            if state == PageState.OK:
                _record_success()
                if post_load_wait > 0:
                    interruptible_sleep(post_load_wait, task_id=task_id)
                if attempt > 0:
                    logger.info(f"{log_prefix}第 {attempt} 次刷新后页面恢复正常")
                return True

            if state in {PageState.CHALLENGE, PageState.RATE_LIMITED, PageState.LOGIN_REQUIRED}:
                challenge_hits += 1
                bump_metric(task_id, "risk_hits")
                telemetry.record_event(
                    task_id,
                    "risk_detected",
                    status="running",
                    phase=f"检测到风险页 {state.value}",
                    risk_state=_to_risk_state(state),
                    meta={"reason": reason, "hit": challenge_hits},
                )
                # 首次就提醒用户操作浏览器完成验证
                if challenge_hits == 1:
                    promote_browser_for_manual_interaction(tab, reason=state.value)
                logger.warning(
                    f"{log_prefix}检测到风险页 state={state.value}, reason={reason}, "
                    f"hit={challenge_hits}/{challenge_retry_times}"
                )
                if challenge_hits <= challenge_retry_times:
                    sleep_with_jitter(challenge_cooldown, jitter_ratio=0.1, minimum=0.8)
                    # 冷却后重新检测（不刷新，等用户手动完成验证）
                    recheck_state, _ = detect_page_state(tab)
                    if recheck_state == PageState.OK:
                        _record_success()
                        logger.info(f"{log_prefix}用户已完成验证，页面恢复正常")
                        if post_load_wait > 0:
                            interruptible_sleep(post_load_wait, task_id=task_id)
                        return True
                    continue
                if raise_on_risk:
                    promote_browser_for_manual_interaction(tab, reason=state.value)
                    raise ChallengeSignal(
                        f"检测到 {state.value}，请在浏览器中完成安全验证后点击继续任务",
                        risk_state=_to_risk_state(state),
                    )
                if attempt == max_retries:
                    logger.error(f"{log_prefix}风险页面持续存在，放弃 (url={url[:80]})")
                    return False
                continue

            if is_error_like_state(state):
                extra_cooldown = _record_error()
                if extra_cooldown > 0:
                    sleep_with_jitter(extra_cooldown, jitter_ratio=0.15, minimum=2.0)
                if attempt == max_retries:
                    logger.error(f"{log_prefix}已达最大重试次数 {max_retries}，放弃 (url={url[:80]})")
                    return False
                continue  # 继续重试

            # 兜底：未知状态视为可继续
            _record_success()
            if post_load_wait > 0:
                interruptible_sleep(post_load_wait, task_id=task_id)
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
