"""
微博搜索主入口。
参考 x_searcher.py 的结构，支持断点恢复和检查点保存。

修复：
1. 正确的 Cookie 注入时序（先到域名再注入）
2. Tab 崩溃恢复机制（Target crashed / 超时后重建 tab 并重试）
3. 反爬检测（验证码页面、登录跳转检测）
4. 搜索页等待优化（替代固定 sleep）
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qs, quote, urlparse

from api.services.time_split_policy import resolve_task_time_split
from json_utils import normalize_json_value

from .checkpoints import (
    build_date_split_checkpoint,
    build_page_checkpoint,
    checkpoint_date_ranges,
    checkpoint_mode,
    checkpoint_next_segment_index,
    checkpoint_page,
    checkpoint_posts,
    load_checkpoint,
    same_query_scope,
    save_checkpoint,
)

logger = logging.getLogger(__name__)

# 重试配置
MAX_PAGE_RETRIES = 2
RETRY_DELAY = 5


@dataclass
class WeiboSearchResult:
    """微博搜索结果"""

    posts: list = field(default_factory=list)
    resumed: bool = False


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



def _merge_posts_by_id(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = list(existing)
    seen_ids = {
        str(post.get("id") or post.get("mid") or "").strip()
        for post in merged
        if isinstance(post, dict)
    }

    for post in incoming:
        post_id = str(post.get("id") or post.get("mid") or "").strip()
        if post_id and post_id in seen_ids:
            continue
        if post_id:
            seen_ids.add(post_id)
        merged.append(post)

    return merged


def _filter_posts_by_exclude_ids(posts: list, exclude_ids: Optional[set[str]] = None) -> list:
    if not exclude_ids:
        return posts

    filtered = []
    for post in posts:
        post_id = str(getattr(post, "mid", "") or getattr(post, "id", "") or "").strip()
        if post_id and post_id in exclude_ids:
            continue
        filtered.append(post)
    return filtered


def _record_search_heartbeat(
    task_id: Optional[str],
    *,
    page: Optional[int] = None,
    stage: str,
    meta: Optional[dict] = None,
) -> None:
    if not task_id:
        return
    try:
        from crawler import telemetry as _telemetry

        payload = {"stage": stage}
        if meta:
            payload.update(meta)
        _telemetry.record_event(
            task_id,
            "weibo_page_attempt",
            page=page,
            meta=payload,
        )
    except Exception:
        pass


def _extract_page_num_from_url(url: str) -> Optional[int]:
    if not url:
        return None
    try:
        page_value = parse_qs(urlparse(url).query).get("page", [None])[0]
        if page_value is None:
            return None
        return int(page_value)
    except Exception:
        return None


def _try_reuse_current_search_page(tab, expected_page: int) -> tuple[Optional[str], Optional[str]]:
    try:
        current_url = tab.url or ""
    except Exception as e:
        return None, f"读取当前 URL 失败: {e}"

    current_page = _extract_page_num_from_url(current_url)
    if current_page != expected_page:
        return None, f"当前页码不是目标页: current_page={current_page}, expected_page={expected_page}"

    try:
        html = tab.html or ""
    except Exception as e:
        return None, f"读取当前页面 HTML 失败: {e}"

    if len(html) < 2000:
        return None, "当前页面 HTML 过短，暂不复用"
    return html, None


def _check_anti_crawl(tab) -> Optional[str]:
    """
    检测页面是否触发了反爬拦截。

    Returns:
        None — 正常页面
        str  — 反爬原因描述
    """
    try:
        url = tab.url or ""
        # 1. 跳转到了登录页
        if "passport.weibo.com" in url:
            return "被重定向到登录页（Cookie 可能过期）"
        if "security.weibo.com" in url:
            return "触发安全验证页面"

        # 2. 检查页面内容（使用 DrissionPage 的元素查找）
        # 验证码相关元素
        try:
            html_text = tab.html
            if html_text and len(html_text) < 2000:
                # 页面内容过短，可能是空白或错误页
                if "验证" in html_text or "verify" in html_text.lower():
                    return "页面包含验证码提示"
                if "请登录" in html_text:
                    return "页面要求登录"
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"反爬检测异常（忽略）: {e}")

    return None


def _get_fresh_tab(browser_instance=None):
    """获取一个新的 tab（用于崩溃后恢复）。优先仅创建新 tab，避免 reset 影响并行任务。"""
    if browser_instance is not None:
        return browser_instance.new_tab()
    from crawler.browser import get_new_tab, ensure_browser_alive
    try:
        ensure_browser_alive()
    except Exception:
        pass
    return get_new_tab()


def _rebuild_weibo_tab(account_cookies: Optional[list[dict]] = None, browser_instance=None) -> "ChromiumTab":
    """重建 tab 并注入微博 Cookie，返回就绪的新 tab。失败则抛出异常。"""
    tab = _get_fresh_tab(browser_instance=browser_instance)
    from .cookie_manager import inject_cookies_to_tab
    from .auth import _get_account_cookies
    cookies = _get_account_cookies(account_cookies)
    if cookies:
        tab.get("https://s.weibo.com", timeout=15)
        time.sleep(1)
        inject_cookies_to_tab(tab, cookies)
        time.sleep(1)
    try:
        tab.set.load_mode.eager()
    except Exception as e:
        logger.debug("重建微博 Tab 后设置 eager 失败（忽略）: %s", e)
    return tab


def _get_tab_with_retry(max_retries: int = 2, browser_instance=None):
    """
    带重试的 tab 获取。
    优先通过 ensure_browser_alive 恢复，仅在最后一次重试才 reset_browser。
    避免跨平台并发时 reset 影响正在运行的 X 爬虫任务。
    池模式下使用指定的 browser_instance。
    """
    if browser_instance is not None:
        # 池模式：直接从指定实例创建 tab，不做全局重置
        for attempt in range(max_retries + 1):
            try:
                return browser_instance.new_tab()
            except Exception as e:
                logger.warning(f"[BrowserPool] 从实例创建 Tab 失败 (attempt {attempt+1}): {e}")
                if attempt < max_retries:
                    time.sleep(2)
        raise RuntimeError("[BrowserPool] 无法从浏览器实例创建 Tab")

    from crawler.browser import get_new_tab, ensure_browser_alive, reset_browser
    for attempt in range(max_retries + 1):
        try:
            tab = get_new_tab()
            return tab
        except Exception as e:
            logger.warning(
                f"获取浏览器 Tab 失败 (attempt {attempt + 1}/{max_retries + 1}): {e}"
            )
            if attempt < max_retries:
                logger.info("正在尝试恢复浏览器连接...")
                try:
                    ensure_browser_alive()
                except Exception:
                    pass
                time.sleep(3)
            else:
                # 最后手段：重置整个浏览器
                logger.warning("所有恢复尝试均失败，执行浏览器重置...")
                try:
                    reset_browser()
                except Exception:
                    pass
                time.sleep(3)
                return get_new_tab()


def _safe_get_html(tab, url: str, wait_seconds: float = 1.0) -> tuple[Optional[str], Optional[str]]:
    """
    安全获取页面 HTML。

    Returns:
        (html, error) — 成功时 error 为 None，失败时 html 为 None
    """
    def _safe_read_tab_url() -> tuple[str, Optional[str]]:
        try:
            value = tab.url
            return value or "", None
        except Exception as e:
            return "", f"读取 tab.url 失败: {e}"

    def _safe_read_tab_html() -> tuple[str, Optional[str]]:
        try:
            value = tab.html
            return value or "", None
        except Exception as e:
            return "", f"读取 tab.html 失败: {e}"

    def _extract_html_from_snapshot(current_url: str, html: str) -> tuple[Optional[str], Optional[str]]:
        from .http_418_guard import detect_weibo_http_418

        if "s.weibo.com" in url and current_url:
            if "s.weibo.com" not in current_url:
                return None, f"被重定向到非搜索页: {current_url}"

        if html:
            html_lower = html.lower()
            if "passport.weibo.com" in current_url or "请登录" in html:
                return None, "反爬拦截: 被重定向到登录页（Cookie 可能过期）"
            if "security.weibo.com" in current_url:
                return None, "反爬拦截: 触发安全验证页面"
            if len(html) < 2000 and ("验证" in html or "verify" in html_lower):
                return None, "反爬拦截: 页面包含验证码提示"

        try:
            if detect_weibo_http_418(tab):
                return None, "微博 HTTP 418 错误页"
        except Exception:
            pass

        if not html:
            return None, "页面 HTML 为空"
        return html, None

    def _try_js_navigate_and_collect_html() -> tuple[Optional[str], Optional[str]]:
        if "s.weibo.com/weibo" not in url or not hasattr(tab, "run_js"):
            return None, "js_navigation_not_applicable"

        try:
            tab.run_js(f"window.location.href = {json.dumps(url)}", timeout=2)
        except Exception as e:
            return None, f"js 导航失败: {e}"

        deadline = time.monotonic() + 15.0  # JS 导航轮询加长到 15 秒
        last_reason = "js 导航后页面尚未就绪"
        while time.monotonic() < deadline:
            try:
                snapshot = tab.run_js(
                    """
                    return {
                      href: location.href || "",
                      readyState: document.readyState || "",
                      bodyTextLength: document.body && document.body.innerText ? document.body.innerText.length : 0,
                      cardCount: document.querySelectorAll('.card-wrap').length || 0,
                      htmlLength: document.documentElement ? document.documentElement.outerHTML.length : 0
                    };
                    """,
                    timeout=3,
                )
            except Exception as e:
                # run_js 失败说明 CDP 执行上下文还在切换中，快速重试
                last_reason = f"js 状态探测失败: {e}"
                time.sleep(0.3)
                continue

            if not isinstance(snapshot, dict):
                last_reason = "js 状态探测返回值异常"
                time.sleep(0.3)
                continue

            current_url = str(snapshot.get("href") or "")
            ready_state = str(snapshot.get("readyState") or "")
            body_text_length = int(snapshot.get("bodyTextLength") or 0)
            card_count = int(snapshot.get("cardCount") or 0)
            html_length = int(snapshot.get("htmlLength") or 0)

            page_looks_ready = (
                "s.weibo.com" in current_url
                and ready_state in ("interactive", "complete")
                and (card_count > 0 or body_text_length > 500 or html_length > 4000)
            )
            if not page_looks_ready:
                last_reason = (
                    f"readyState={ready_state}, cardCount={card_count}, "
                    f"bodyTextLength={body_text_length}, htmlLength={html_length}"
                )
                time.sleep(0.3)
                continue

            # ── 校验页码是否与目标一致 ────────────────────────────────────────
            # 微博翻页有时会因为浏览器状态跳到其他页码（如 page=4 而非 3），
            # 此时必须等待继续导航，不能拿错误页面的 HTML 直接使用。
            from urllib.parse import urlparse, parse_qs
            try:
                target_page = parse_qs(urlparse(url).query).get("page", [None])[0]
                actual_page = parse_qs(urlparse(current_url).query).get("page", [None])[0]
                if target_page and actual_page and target_page != actual_page:
                    last_reason = (
                        f"URL 页码不匹配：目标 page={target_page}，"
                        f"当前 page={actual_page}，等待导航完成"
                    )
                    logger.debug("[safe_get_html] %s", last_reason)
                    time.sleep(0.5)
                    continue
            except Exception:
                pass  # URL 解析失败时不阻塞，继续走正常流程

            try:
                html = tab.run_js(
                    "return document.documentElement ? document.documentElement.outerHTML : ''",
                    timeout=3,
                ) or ""
            except Exception as e:
                last_reason = f"js 提取 HTML 失败: {e}"
                time.sleep(0.3)
                continue

            parsed_html, parsed_error = _extract_html_from_snapshot(current_url, str(html))
            if parsed_html:
                logger.info("微博搜索页使用 JS 导航快速就绪路径成功")
                return parsed_html, None
            last_reason = parsed_error or last_reason
            time.sleep(0.3)

        return None, last_reason

    def _extract_current_tab_html(*, from_timeout: bool = False) -> tuple[Optional[str], Optional[str]]:
        from .http_418_guard import detect_weibo_http_418

        # 检查是否被重定向到非搜索页面
        current_url, url_error = _safe_read_tab_url()
        if "s.weibo.com" in url and current_url:
            if "s.weibo.com" not in current_url:
                return None, f"被重定向到非搜索页: {current_url}"

        # 检查反爬
        try:
            anti_crawl_reason = _check_anti_crawl(tab)
        except Exception as e:
            anti_crawl_reason = None
            anti_crawl_error = f"反爬检测异常: {e}"
        else:
            anti_crawl_error = None
        if anti_crawl_reason:
            return None, f"反爬拦截: {anti_crawl_reason}"

        try:
            if detect_weibo_http_418(tab):
                return None, "微博 HTTP 418 错误页"
        except Exception as e:
            detect_418_error = f"418 检测异常: {e}"
        else:
            detect_418_error = None

        html, html_error = _safe_read_tab_html()
        if not html:
            diagnostics = [msg for msg in (url_error, html_error, anti_crawl_error, detect_418_error) if msg]
            if from_timeout and diagnostics:
                return None, "；".join(diagnostics)
            return None, "页面 HTML 为空"

        # `Page.stopLoading` 超时时，浏览器/标签页可能仍正常，DOM 也可能已经就绪。
        # 这里允许在 timeout 后直接复用已得到的页面内容，避免误判为浏览器卡死。
        if from_timeout and len(html) <= 2000:
            return None, "页面 HTML 过短，疑似未加载完成"
        return html, None

    js_html, js_error = _try_js_navigate_and_collect_html()
    if js_html:
        return js_html, None

    # ── JS 导航已触发但提取失败时，先用 tab.html 尝试读取已加载的页面 ──────
    # window.location.href 已触发浏览器导航，页面可能已经加载好；
    # 但 tab.run_js() 因 CDP 上下文切换失败无法提取 HTML。
    # 此处用 DrissionPage 原生属性 tab.html（内部会正确处理上下文切换）来读取，
    # 避免 tab.get() 对同一 URL 双重导航（触发微博反爬）。
    js_did_navigate = (
        js_error
        and js_error != "js_navigation_not_applicable"
        and not js_error.startswith("js 导航失败")
    )
    if js_did_navigate:
        logger.debug("JS 导航已触发但 run_js 提取失败 (%s)，尝试 tab.html 等待页面就绪...", js_error)
        for _wait_i in range(8):  # 最多等 4s（0.5s × 8）
            time.sleep(0.5)
            recovered_html, recovered_error = _extract_current_tab_html()
            if recovered_html:
                logger.info("JS 导航后通过 tab.html 成功提取页面内容（等待 %.1fs）", (_wait_i + 1) * 0.5)
                return recovered_html, None
        logger.debug("JS 导航后 tab.html 仍未能提取，回退到 tab.get(): %s", recovered_error)

    if js_error and js_error != "js_navigation_not_applicable":
        logger.debug("微博搜索页 JS 导航快速路径未成功，回退 tab.get: %s", js_error)

    try:
        tab.get(url, timeout=20)

        # 动态等待：先等一个较短的基础时间，然后检测页面内容是否就绪
        time.sleep(wait_seconds)

        # 快速检查页面是否已加载内容（最多额外等 1.5s）
        for _ in range(3):
            html_check = tab.html
            if html_check and len(html_check) > 2000:
                break
            time.sleep(0.5)

        return _extract_current_tab_html()
    except Exception as e:
        error_str = str(e)
        err_lower = error_str.lower()
        if "timeout" in err_lower and "disconnect" not in err_lower and "crashed" not in err_lower:
            recovered_html, recovered_error = _extract_current_tab_html(from_timeout=True)
            if recovered_html:
                logger.info("微博搜索页导航超时，但当前 DOM 已可用，继续使用已加载页面")
                return recovered_html, None
            return None, (
                "[timeout] 页面导航超时（Page.stopLoading 未在超时内返回，"
                f"浏览器/标签页可能仍在线）; detail={recovered_error or error_str}"
            )
        return None, error_str


def _prepare_search_session(tab, task_id: Optional[str], slot_id: Optional[int] = None) -> None:
    """为微博搜索准备一次性会话状态，避免每个时间分段都回到主页重新初始化。"""
    from api.services.task_manager import update_task_phase
    from .auth import ensure_weibo_login, ensure_search_cookies
    from .account_pool import get_weibo_pool

    # 按 slot_id 选择账号 Cookie，确保不同 slot 用不同账号
    account_cookies = None
    if slot_id is not None:
        try:
            pool = get_weibo_pool()
            account = pool.pick_account_by_index(slot_id)
            if account and account.cookies:
                account_cookies = account.cookies
                logger.info(f"微博 slot #{slot_id} 使用账号: {account.alias!r}")
        except Exception as e:
            logger.warning(f"按 slot 选择微博账号失败: {e}")

    if task_id:
        update_task_phase(task_id, "正在验证微博登录状态...")
    try:
        logged_in = ensure_weibo_login(tab, account_cookies=account_cookies)
        if not logged_in:
            logger.warning("微博未登录，将以游客模式尝试（可能受限）")
    except Exception as e:
        logger.warning(f"微博登录验证失败: {e}")

    if task_id:
        update_task_phase(task_id, "正在准备搜索 Cookie...")
    try:
        ensure_search_cookies(tab, account_cookies=account_cookies)
    except Exception as e:
        logger.warning(f"搜索 Cookie 准备失败: {e}")

    try:
        tab.set.load_mode.eager()
        logger.debug("已将搜索 Tab 设为 eager 加载模式（DOM 就绪即完成）")
    except Exception as e:
        logger.warning(f"设置 eager 加载模式失败: {e}")


def _close_tab_safe(tab, label: str = "") -> None:
    """安全关闭 tab，忽略所有异常并记录日志。"""
    if tab is None:
        return
    try:
        tab.close()
        if label:
            logger.debug(f"Tab 已关闭: {label}")
    except Exception as e:
        logger.debug(f"关闭 Tab 失败（忽略）{label}: {e}")


def _count_browser_tabs(browser_instance) -> int:
    """获取浏览器实例当前的 tab 数量（用于诊断）。"""
    try:
        if browser_instance is not None:
            browser = browser_instance.get_browser()
        else:
            from crawler.browser import get_browser
            browser = get_browser()
        return len(browser.tab_ids)
    except Exception:
        return -1


def search(
    keyword: str,
    task_id: Optional[str] = None,
    resume: bool = True,
    fetch_comments: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    time_split_mode: str = "inherit",
    time_split_window_days: Optional[int] = None,
    time_split_max_segments: Optional[int] = None,
    _parent_accumulated: Optional[list] = None,
    _tab=None,
    _session_ready: bool = False,
    _query_plan_resolved: bool = False,
    browser_instance=None,
    comment_browser_instance=None,
    slot_id: Optional[int] = None,
    exclude_ids: Optional[set[str]] = None,
    seed_posts: Optional[list[dict]] = None,
) -> WeiboSearchResult:
    """
    微博关键词搜索主入口。
    返回 WeiboSearchResult，其中 posts 是 WeiboPost.to_dict() 的列表。
    """
    from config import settings
    from api.services.task_manager import (
        update_preview_tweets,
        update_task_phase,
        update_task_segment_progress,
        update_task_reply_snapshot,
    )
    from crawler.utils import check_signal, StopSignal, jittered_sleep, interruptible_sleep
    from .html_parser import parse_search_page
    from .http_418_guard import wait_weibo_http_418_cooldown
    from .comment_fetcher import fetch_comments as do_fetch_comments
    from .query_planner import build_weibo_query_plan

    owns_tab = _tab is None
    tab = _tab or _get_tab_with_retry(browser_instance=browser_instance)

    # ── 预先提取 account_cookies，供后续 Tab 重建复用 ──────────────
    _account_cookies_for_rebuild: Optional[list[dict]] = None
    if slot_id is not None:
        try:
            from .account_pool import get_weibo_pool
            pool = get_weibo_pool()
            account = pool.pick_account_by_index(slot_id)
            if account and account.cookies:
                _account_cookies_for_rebuild = account.cookies
        except Exception:
            pass

    # Tab 重建计数器（断路器：同一个 search() 调用中最多重建 N 次）
    _MAX_TAB_REBUILDS = 10
    _tab_rebuild_count = 0

    def _do_rebuild_tab(old_tab) -> "ChromiumTab":
        """关闭旧 tab 并重建新 tab，带断路器保护。"""
        nonlocal _tab_rebuild_count
        _tab_rebuild_count += 1
        if _tab_rebuild_count > _MAX_TAB_REBUILDS:
            logger.error(
                f"Tab 重建次数已达上限 {_MAX_TAB_REBUILDS}，停止重建以避免资源泄漏"
            )
            raise RuntimeError(f"Too many tab rebuilds ({_MAX_TAB_REBUILDS})")

        _close_tab_safe(old_tab, label=f"rebuild #{_tab_rebuild_count}")

        tab_count = _count_browser_tabs(browser_instance)
        logger.info(
            f"Tab 重建 #{_tab_rebuild_count}/{_MAX_TAB_REBUILDS}，"
            f"当前浏览器 tab 数: {tab_count}"
        )

        return _rebuild_weibo_tab(
            account_cookies=_account_cookies_for_rebuild,
            browser_instance=browser_instance,
        )

    try:
        # ── 1. 登录验证 + 搜索 Cookie 准备（仅首次执行）──────────────
        if not _session_ready:
            _prepare_search_session(tab, task_id, slot_id=slot_id)

        if not _query_plan_resolved:
            query_plan = build_weibo_query_plan(
                keyword,
                enable_or_split=bool(getattr(settings, "weibo_auto_split_or_keywords", False)),
            )
            if query_plan.uses_or_split:
                logger.info(
                    "微博查询包含 OR，拆分为 %s 个子查询: %s",
                    len(query_plan.variants),
                    " | ".join(query_plan.variants),
                )
                if task_id:
                    update_task_phase(
                        task_id,
                        f"微博关键词包含 OR，已拆分为 {len(query_plan.variants)} 个子查询并自动去重..."
                    )

                merged_posts: list[dict] = list(seed_posts or [])
                seed_count = len(merged_posts)
                seen_post_ids: set[str] = set()
                for post in merged_posts:
                    post_id = str(post.get("id") or post.get("mid") or "").strip()
                    if post_id:
                        seen_post_ids.add(post_id)
                try:
                    for variant_idx, variant_keyword in enumerate(query_plan.variants):
                        check_signal(task_id)
                        if task_id:
                            update_task_phase(
                                task_id,
                                f"正在执行微博子查询 {variant_idx + 1}/{len(query_plan.variants)}: {variant_keyword}"
                            )

                        variant_result = search(
                            keyword=variant_keyword,
                            task_id=task_id,
                            resume=False,
                            fetch_comments=fetch_comments,
                            start_date=start_date,
                            end_date=end_date,
                            time_split_mode=time_split_mode,
                            time_split_window_days=time_split_window_days,
                            time_split_max_segments=time_split_max_segments,
                            _tab=tab,
                            _session_ready=True,
                            _query_plan_resolved=True,
                            browser_instance=browser_instance,
                            comment_browser_instance=comment_browser_instance,
                            slot_id=slot_id,
                            exclude_ids=exclude_ids,
                        )
                        for post in variant_result.posts:
                            post_id = str(post.get("id") or post.get("mid") or "").strip()
                            if post_id and post_id in seen_post_ids:
                                continue
                            if post_id:
                                seen_post_ids.add(post_id)
                            merged_posts.append(post)

                        if task_id:
                            update_preview_tweets(
                                task_id,
                                current_page=variant_idx + 1,
                                tweets_for_preview=merged_posts,
                            )
                except StopSignal:
                    logger.info(f"收到停止信号，微博 OR 子查询终止 task_id={task_id}")
                else:
                    logger.info(
                        "微博 OR 查询完成：%s 个子查询，去重后 %s 条",
                        len(query_plan.variants),
                        len(merged_posts),
                    )
                return WeiboSearchResult(posts=merged_posts, resumed=False)

        # ── 3. 断点恢复 ──────────────────────────────────────────
        checkpoint: dict = {}
        if resume and task_id:
            loaded_checkpoint = load_checkpoint(task_id)
            if same_query_scope(
                loaded_checkpoint,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
            ):
                checkpoint = loaded_checkpoint
            elif loaded_checkpoint:
                logger.info(
                    "微博断点与当前查询范围不一致，忽略旧断点: task_id=%s",
                    task_id,
                )

        start_page: int = checkpoint_page(checkpoint, 1)
        seed_posts = seed_posts or []
        seed_count = len(seed_posts) if _parent_accumulated is None else 0
        all_posts_dicts: list[dict] = _merge_posts_by_id(seed_posts, checkpoint_posts(checkpoint))
        resumed = bool(checkpoint)
        ckpt_mode = checkpoint_mode(checkpoint)
        split_config = resolve_task_time_split(
            platform="weibo",
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            time_split_mode=time_split_mode,
            time_split_window_days=time_split_window_days,
            time_split_max_segments=time_split_max_segments,
        )

        max_pages: int = settings.weibo_max_pages
        page_interval: float = settings.weibo_search_page_interval

        # ── 评论 Pipeline 初始化（fetch_comments=True 时启用双 Tab 并发）──
        _comment_pipeline = None
        if fetch_comments:
            from crawler.pipeline import WeiboCommentPipeline
            from crawler import telemetry as _telemetry
            from api.services.reply_tree import count_reply_tree_nodes

            def _on_comment_done(mid: str, comments: list) -> None:
                normalized_comments = normalize_json_value(comments)
                if task_id:
                    update_task_reply_snapshot(task_id, mid, normalized_comments)
                    reply_total = count_reply_tree_nodes(normalized_comments)
                    if reply_total > 0:
                        _telemetry.record_event(
                            task_id,
                            "weibo_comment_done",
                            delta_replies=reply_total,
                        )

            _comment_pipeline = WeiboCommentPipeline(
                task_id=task_id,
                browser_instance=browser_instance,
                comment_browser_instance=comment_browser_instance,
                on_comment_done=_on_comment_done,
            )

        # ── 日期范围分割（突破 50 页限制）────────────────────────
        # 注意：如果 _parent_accumulated 不为 None，说明当前调用已经是父级分段的子段，
        # 不应再次分割，否则会导致 43 个月 × 10 个子段 = 430 个切片的指数级膨胀
        if split_config.enabled and start_date and end_date and _parent_accumulated is None:
            from .date_splitter import split_date_range

            date_ranges = checkpoint_date_ranges(checkpoint) if ckpt_mode == "date_split" else []
            if not date_ranges:
                date_ranges = split_date_range(
                    start_date,
                    end_date,
                    max_pages=max_pages,
                    window_days=split_config.window_days,
                    max_segments=split_config.max_segments,
                )

            should_use_date_split = len(date_ranges) > 1 and (
                not resumed or ckpt_mode == "date_split" or start_page > max_pages
            )
            if should_use_date_split:
                if resumed and ckpt_mode == "page" and start_page > max_pages:
                    logger.info(
                        "检测到旧页级断点已到达微博 50 页上限，自动切换为时间分段续爬: task_id=%s, next_page=%s",
                        task_id,
                        start_page,
                    )
                    if task_id:
                        update_task_phase(
                            task_id,
                            "检测到已达到微博单次 50 页上限，自动切换为时间分段继续抓取...",
                        )

                logger.info(
                    f"日期范围已分割为 {len(date_ranges)} 个子范围，将依次搜索"
                )
                # ⚠️ 必须先初始化 start_segment_index 和 all_results，
                # 再调用 update_task_segment_progress，否则会触发 NameError
                all_results: list[dict] = _merge_posts_by_id(seed_posts, checkpoint_posts(checkpoint))
                start_segment_index = checkpoint_next_segment_index(checkpoint) if ckpt_mode == "date_split" else 0
                if task_id:
                    update_task_segment_progress(
                        task_id,
                        _build_segment_progress(
                            enabled=True,
                            total_segments=len(date_ranges),
                            completed_segments=max(0, start_segment_index),
                            current_segment_index=max(1, start_segment_index + 1),
                            current_since=date_ranges[start_segment_index][0] if start_segment_index < len(date_ranges) else None,
                            current_until=date_ranges[start_segment_index][1] if start_segment_index < len(date_ranges) else None,
                        ),
                    )
                if task_id:
                    update_task_phase(
                        task_id,
                        f"日期范围已拆分为 {len(date_ranges)} 段，开始分段搜索..."
                    )
                if all_results and task_id:
                    update_preview_tweets(
                        task_id,
                        current_page=start_segment_index,
                        tweets_for_preview=all_results,
                    )
                try:
                    for seg_idx in range(start_segment_index, len(date_ranges)):
                        seg_start, seg_end = date_ranges[seg_idx]
                        check_signal(task_id)  # 支持 pause/stop

                        # ── 分段间间隔：避免分段切换时无间隔地连续请求 ──
                        if seg_idx > start_segment_index:
                            seg_interval = page_interval * random.uniform(1.0, 1.5)
                            logger.debug("微博分段间间隔: seg=%d, interval=%.1fs", seg_idx, seg_interval)
                            interruptible_sleep(seg_interval, task_id=task_id)

                        if task_id:
                            update_task_segment_progress(
                                task_id,
                                _build_segment_progress(
                                    enabled=True,
                                    total_segments=len(date_ranges),
                                    completed_segments=seg_idx,
                                    current_segment_index=seg_idx + 1,
                                    current_since=seg_start,
                                    current_until=seg_end,
                                ),
                            )
                            update_task_phase(
                                task_id,
                                f"正在搜索第 {seg_idx + 1}/{len(date_ranges)} 段: "
                                f"{seg_start} ~ {seg_end}"
                            )
                        # 递归调用自身，每段单独搜索
                        seg_result = search(
                            keyword=keyword,
                            task_id=task_id,
                            resume=False,
                            fetch_comments=False,  # 分片阶段只搜帖子，全部分片完成后统一抓评论
                            start_date=seg_start,
                            end_date=seg_end,
                            _parent_accumulated=all_results,
                            _tab=tab,
                            _session_ready=True,
                            browser_instance=browser_instance,
                            comment_browser_instance=comment_browser_instance,
                            slot_id=slot_id,
                            exclude_ids=exclude_ids,
                            time_split_mode=time_split_mode,
                            time_split_window_days=time_split_window_days,
                            time_split_max_segments=time_split_max_segments,
                        )
                        all_results = _merge_posts_by_id(all_results, seg_result.posts)
                        # 实时推送合并后的预览
                        if task_id:
                            update_task_segment_progress(
                                task_id,
                                _build_segment_progress(
                                    enabled=True,
                                    total_segments=len(date_ranges),
                                    completed_segments=seg_idx + 1,
                                    current_segment_index=min(seg_idx + 2, len(date_ranges)),
                                    current_since=date_ranges[seg_idx + 1][0] if seg_idx + 1 < len(date_ranges) else None,
                                    current_until=date_ranges[seg_idx + 1][1] if seg_idx + 1 < len(date_ranges) else None,
                                ),
                            )
                            update_preview_tweets(
                                task_id,
                                current_page=seg_idx + 1,
                                tweets_for_preview=all_results,
                            )
                            save_checkpoint(
                                task_id,
                                build_date_split_checkpoint(
                                    keyword=keyword,
                                    start_date=start_date,
                                    end_date=end_date,
                                    date_ranges=date_ranges,
                                    next_segment_index=seg_idx + 1,
                                    posts=all_results,
                                ),
                            )
                except StopSignal:
                    logger.info(f"收到停止信号，微博分段搜索终止 task_id={task_id}")
                else:
                    logger.info(
                        "微博分段搜索完成：共 %s 段，累计 %s 条",
                        len(date_ranges),
                        len(all_results),
                    )
                    if task_id:
                        update_task_segment_progress(
                            task_id,
                            _build_segment_progress(
                                enabled=True,
                                total_segments=len(date_ranges),
                                completed_segments=len(date_ranges),
                                current_segment_index=len(date_ranges),
                                current_since=date_ranges[-1][0] if date_ranges else None,
                                current_until=date_ranges[-1][1] if date_ranges else None,
                            ),
                        )

                # ── 所有分片搜完后，统一抓评论（不在每段内部阻塞等待）──────────
                if fetch_comments and all_results:
                    if task_id:
                        update_task_phase(
                            task_id,
                            f"所有分段搜索完成（{len(all_results)} 条微博），开始统一抓取评论...",
                        )
                    logger.info(
                        "微博分段搜索全部完成，开始统一抓取 %s 条帖子的评论",
                        len(all_results),
                    )
                    # 复用单段搜索的 search() 来完成评论抓取（仅传 all_results 作 seed，不搜索）
                    from .comment_fetcher import fetch_comments as do_fetch_comments
                    from .comment_stats import build_comment_stats, collect_comment_tree_stats
                    from crawler import telemetry as _telemetry

                    updated: list[dict] = []
                    for post_idx, post_dict in enumerate(all_results):
                        check_signal(task_id)
                        post_comments_count = post_dict.get("comments_count", 0)
                        if not fetch_comments or not post_comments_count:
                            updated.append(post_dict)
                            continue
                        mid = post_dict.get("mid") or post_dict.get("id") or ""
                        if task_id:
                            update_task_phase(
                                task_id,
                                f"统一评论抓取 {post_idx + 1}/{len(all_results)}: mid={mid}",
                            )
                        try:
                            from config import settings as _settings
                            comment_result = do_fetch_comments(
                                mid,
                                author_uid=post_dict.get("author_id", ""),
                                post_url=post_dict.get("url", ""),
                                post_comment_count=post_comments_count,
                                max_comments=_settings.weibo_max_comments_per_post,
                                page_interval=_settings.weibo_comment_page_interval,
                                task_id=task_id,
                                browser_instance=comment_browser_instance or browser_instance,
                            )
                            tree_stats = collect_comment_tree_stats(comment_result.comments)
                            comment_stats = build_comment_stats(
                                post_comment_count=post_comments_count,
                                api_claimed_total=comment_result.api_claimed_total,
                                fetched_total_count=tree_stats.total_count,
                                fetched_top_level_count=tree_stats.top_level_count,
                                max_depth=tree_stats.max_depth,
                                sub_comment_completion_status=comment_result.sub_comment_completion_status,
                                truncated_reason=comment_result.truncated_reason,
                                pages_fetched=comment_result.pages_fetched,
                            )
                            new_dict = dict(post_dict)
                            new_dict["replies"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in comment_result.comments]
                            new_dict["comment_stats"] = comment_stats.__dict__ if hasattr(comment_stats, "__dict__") else comment_stats
                            if task_id:
                                update_task_reply_snapshot(
                                    task_id,
                                    str(mid),
                                    new_dict["replies"],
                                    comment_stats=new_dict["comment_stats"],
                                )
                            updated.append(new_dict)
                            if task_id and tree_stats.total_count > 0:
                                _telemetry.record_event(
                                    task_id,
                                    "weibo_comment_done",
                                    delta_replies=tree_stats.total_count,
                                )
                        except StopSignal:
                            updated.append(post_dict)
                            updated.extend(all_results[post_idx + 1:])
                            all_results = updated
                            raise
                        except Exception as e:
                            logger.warning(f"统一评论抓取失败 mid={mid}: {e}")
                            updated.append(post_dict)
                    all_results = updated
                    if task_id:
                        update_preview_tweets(task_id, current_page=len(date_ranges), tweets_for_preview=all_results)

                return WeiboSearchResult(posts=all_results, resumed=resumed)

        # 构建搜索 URL
        kw_encoded = quote(keyword)

        consecutive_errors = 0  # 连续错误计数
        consecutive_timeouts = 0  # 连续 timeout 计数（用于检测系统资源不足）
        _MAX_CONSECUTIVE_TIMEOUTS = 5  # 连续 5 次 timeout 终止搜索

        try:
            for page in range(start_page, max_pages + 1):
                # 检查暂停/停止信号
                check_signal(task_id)

                # 构建 URL
                url = f"https://s.weibo.com/weibo?q={kw_encoded}&typeall=1&suball=1&count=50&page={page}"
                if start_date and end_date:
                    url += f"&timescope=custom:{start_date}:{end_date}"

                logger.info(f"微博搜索第 {page} 页: {url}")
                if task_id:
                    update_task_phase(task_id, f"正在获取微博搜索第 {page} 页...")
                _record_search_heartbeat(
                    task_id,
                    page=page,
                    stage="page_start",
                    meta={"url": url},
                )

                # ── 带重试的页面获取 ──────────────
                html = None
                page_error = None

                # ── 优先路径：第 2 页起通过点击"下一页"按钮翻页 ──
                # 点击翻页按钮是真实用户行为，不容易触发微博反爬风控；
                # 直接 URL 导航则容易被检测为机器人。
                _used_click_pagination = False
                _click_attempted = False
                if page > start_page:
                    reused_html, reused_error = _try_reuse_current_search_page(tab, expected_page=page)
                    if reused_html:
                        html = reused_html
                        logger.info("微博第 %d 页检测到当前 Tab 已在目标页，直接复用当前页面", page)
                    else:
                        _click_attempted = True
                        from .pagination import click_next_page

                        _record_search_heartbeat(
                            task_id,
                            page=page,
                            stage="click_pagination_start",
                        )
                        click_html, click_error = click_next_page(
                            tab, expected_page=page, timeout=15.0,
                        )
                        if click_html:
                            html = click_html
                            _used_click_pagination = True
                            consecutive_timeouts = 0
                            logger.debug("微博第 %d 页使用点击翻页成功", page)
                        else:
                            click_error_str = click_error or ""
                            # CDP 连接死亡 → 必须重建 tab，不可能恢复
                            if "CDP_DEAD" in click_error_str:
                                logger.warning(
                                    "微博第 %d 页 CDP 连接已死，重建 Tab 并用 URL 导航...",
                                    page,
                                )
                                try:
                                    tab = _do_rebuild_tab(tab)
                                    _record_search_heartbeat(
                                        task_id,
                                        page=page,
                                        stage="tab_rebuilt_after_click_cdp_dead",
                                    )
                                    logger.info("Tab 重建成功，将用 URL 导航第 %d 页", page)
                                except RuntimeError:
                                    logger.error("Tab 重建次数超限，终止搜索")
                                    break
                                except Exception as e:
                                    logger.error("Tab 重建失败: %s", e)
                            else:
                                logger.info(
                                    "微博第 %d 页点击翻页失败 (%s)，回退到 URL 导航",
                                    page, click_error,
                                )

                            if reused_error:
                                logger.debug("微博第 %d 页未复用当前页: %s", page, reused_error)

                # ── 回退路径：URL 导航（第 1 页、断点恢复、点击失败时使用）──
                if not html:
                    for retry in range(MAX_PAGE_RETRIES + 1):
                        _record_search_heartbeat(
                            task_id,
                            page=page,
                            stage="url_navigation_attempt",
                            meta={"retry": retry},
                        )
                        html, page_error = _safe_get_html(tab, url)
                        if html:
                            consecutive_timeouts = 0  # 成功获取页面，重置 timeout 计数
                            break

                        # 错误处理
                        error_lower = (page_error or "").lower()
                        is_timeout = "[timeout]" in error_lower or (
                            "timeout" in error_lower
                            and "disconnect" not in error_lower
                            and "crashed" not in error_lower
                        )
                        
                        # 严重的 CDP 底层超时，代表管道已堵死或浏览器卡死，不可恢复
                        is_severe_cdp_timeout = "timeout" in error_lower and any(kw in error_lower for kw in (
                            "target.gettargetinfo", 
                            "dom.getouterhtml", 
                            "page.stoploading",
                            "浏览器卡了"
                        ))
                        
                        if is_severe_cdp_timeout:
                            is_timeout = False  # 不要走只 sleep 重试的路径
                            logger.error("检测到严重的底层 CDP 超时，Tab 已实质性死亡。")

                        # 只有真正的 crash/disconnect 或者底层 CDP 堵死才算 tab 死亡
                        is_tab_dead = (
                            any(kw in error_lower for kw in (
                                "crashed", "连接已断开",
                                "disconnected", "connection lost", "target closed",
                            ))
                            and not is_timeout
                        ) or is_severe_cdp_timeout
                        logger.warning(
                            f"获取微博搜索页失败 page={page} retry={retry}/{MAX_PAGE_RETRIES}: {page_error}"
                        )

                        if is_timeout:
                            consecutive_timeouts += 1
                            if consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS:
                                logger.error(
                                    f"连续 {consecutive_timeouts} 次 timeout，"
                                    f"系统可能资源不足，终止搜索"
                                )
                                break

                        if is_timeout and retry < MAX_PAGE_RETRIES:
                            # 检查浏览器是否被标记了延迟回收（内存超标）
                            # 如果是，超时很可能是内存压力导致的，走重建路径释放内存
                            _needs_rebuild = (
                                browser_instance is not None
                                and getattr(browser_instance, "_recycle_requested", False)
                            )
                            if _needs_rebuild:
                                logger.info(
                                    "页面超时且浏览器已标记内存回收，走重建路径释放内存..."
                                )
                                try:
                                    tab = _do_rebuild_tab(tab)
                                    _record_search_heartbeat(
                                        task_id,
                                        page=page,
                                        stage="tab_rebuilt_after_timeout",
                                        meta={"retry": retry},
                                    )
                                except RuntimeError:
                                    logger.error("Tab 重建次数超限，终止搜索")
                                    break
                                except Exception as e:
                                    logger.error(f"内存回收重建 Tab 失败: {e}")
                                interruptible_sleep(RETRY_DELAY, task_id=task_id)
                            else:
                                # 页面导航超时：tab 本身还活着，不等同于浏览器卡死。
                                # 先等待一小段时间再重试，避免对微博搜索页过度重建。
                                logger.info(
                                    f"页面导航超时（tab 仍在线，未判定浏览器卡死），在原 tab 上重试... "
                                    f"(retry {retry + 1}/{MAX_PAGE_RETRIES}), "
                                    f"连续 timeout: {consecutive_timeouts}/{_MAX_CONSECUTIVE_TIMEOUTS}"
                                )
                                interruptible_sleep(RETRY_DELAY * 2, task_id=task_id)
                        elif is_tab_dead and retry < MAX_PAGE_RETRIES:
                            # Tab 崩溃 / 连接断开：先关闭旧 tab 再重建，防止 tab 泄漏
                            logger.info("检测到 Tab 崩溃/断开连接，正在重建...")
                            try:
                                tab = _do_rebuild_tab(tab)
                                _record_search_heartbeat(
                                    task_id,
                                    page=page,
                                    stage="tab_rebuilt_after_disconnect",
                                    meta={"retry": retry},
                                )
                            except RuntimeError:
                                logger.error("Tab 重建次数超限，终止搜索")
                                break
                            except Exception as e:
                                logger.error(f"重建 Tab 失败: {e}")
                            interruptible_sleep(RETRY_DELAY, task_id=task_id)
                        elif "http 418" in error_lower and retry < MAX_PAGE_RETRIES:
                            wait_weibo_http_418_cooldown(
                                task_id=task_id,
                                cooldown_seconds=float(
                                    getattr(settings, "weibo_http_418_cooldown_seconds", 600.0)
                                ),
                                context="搜索页",
                                phase_callback=(lambda msg: update_task_phase(task_id, msg)) if task_id else None,
                            )
                            try:
                                tab = _do_rebuild_tab(tab)
                                _record_search_heartbeat(
                                    task_id,
                                    page=page,
                                    stage="tab_rebuilt_after_http_418",
                                    meta={"retry": retry},
                                )
                            except RuntimeError:
                                logger.error("Tab 重建次数超限，终止搜索")
                                break
                            except Exception as e:
                                logger.error(f"微博 418 冷却后重建 Tab 失败: {e}")
                        elif "反爬拦截" in (page_error or ""):
                            # 反爬拦截：加大延迟后重试
                            wait = RETRY_DELAY * (retry + 1) * 2
                            logger.warning(f"触发反爬，等待 {wait}s 后重试...")
                            time.sleep(wait)
                        else:
                            interruptible_sleep(RETRY_DELAY, task_id=task_id)

                if not html:
                    consecutive_errors += 1
                    logger.error(f"获取微博搜索页最终失败 page={page}: {page_error}")

                    # 连续 timeout 超限 → 重建 tab 并跳页（而非终止搜索）
                    if consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS:
                        logger.warning(
                            f"连续 {consecutive_timeouts} 次 timeout，"
                            f"重建 Tab 并跳过第 {page} 页..."
                        )
                        try:
                            tab = _do_rebuild_tab(tab)
                            consecutive_timeouts = 0  # 重建后重置
                        except RuntimeError:
                            logger.error("Tab 重建次数超限，终止搜索")
                            break
                        except Exception as e:
                            logger.error(f"Tab 重建失败: {e}")

                    # 连接断开 → 重建 tab
                    error_lower_final = (page_error or "").lower()
                    is_truly_disconnected = (
                        any(kw in error_lower_final for kw in (
                            "连接已断开", "disconnected", "connection lost", "target closed",
                        ))
                        and "timeout" not in error_lower_final
                    )
                    if is_truly_disconnected:
                        logger.info("页面最终失败且连接已断开，尝试重建 Tab...")
                        try:
                            tab = _do_rebuild_tab(tab)
                            consecutive_errors = 0
                        except RuntimeError:
                            logger.error("Tab 重建次数超限，终止搜索")
                            break
                        except Exception as e:
                            logger.error(f"Tab 重建失败: {e}")

                    # ── 跳页兜底：连续 3 页失败才终止，否则跳过当前页继续 ──
                    if consecutive_errors >= 3:
                        logger.error("连续 3 页获取失败，终止搜索")
                        break
                    logger.warning(
                        f"第 {page} 页获取失败（连续失败 {consecutive_errors}/3），"
                        f"跳过此页继续爬第 {page + 1} 页"
                    )
                    continue
                else:
                    consecutive_errors = 0

                # ── 解析结果 ─────────────────────
                try:
                    posts, has_next, total_pages = parse_search_page(html)
                    posts = _filter_posts_by_exclude_ids(posts, exclude_ids)
                except Exception as e:
                    logger.error(f"解析微博搜索结果失败 page={page}: {e}")
                    break

                if page == start_page and total_pages > 0:
                    logger.info(f"微博搜索共 {total_pages} 页")
                    if task_id:
                        update_task_phase(
                            task_id,
                            f"微博搜索共 {total_pages} 页，正在获取第 {page} 页..."
                        )

                if not posts:
                    logger.info(f"微博搜索第 {page} 页无结果，终止")
                    break

                if fetch_comments and _comment_pipeline is not None:
                    # ── Pipeline 模式：搜索 tab 不停，评论在 comment_tab 并发抓取 ──
                    if not _comment_pipeline._comment_thread:
                        _comment_pipeline.start()

                    for post in posts:
                        _comment_pipeline.put_batch([post])
                        # 记录帖子（无评论版本先放进 all_posts_dicts，最后再替换）
                        all_posts_dicts.append(post.to_dict())

                    # 检查 comment worker 是否发生致命错误
                    pipeline_err = _comment_pipeline.get_error()
                    if pipeline_err is not None:
                        raise pipeline_err
                else:
                    # ── 原同步模式（fetch_comments=False 或无 pipeline 时）────────
                    for post_idx, post in enumerate(posts):
                        # 按需抓取评论
                        if fetch_comments and post.comments_count > 0:
                            if task_id:
                                update_task_phase(
                                    task_id,
                                    f"正在抓取第 {page} 页第 {post_idx + 1}/{len(posts)} 条微博的评论..."
                                )
                            try:
                                comment_result = do_fetch_comments(
                                    post.mid,
                                    author_uid=post.author_id,
                                    post_url=post.url,
                                    post_comment_count=post.comments_count,
                                    max_comments=settings.weibo_max_comments_per_post,
                                    page_interval=settings.weibo_comment_page_interval,
                                    task_id=task_id,
                                    browser_instance=browser_instance,
                                )
                                post.comments = comment_result.comments
                                from .comment_stats import build_comment_stats, collect_comment_tree_stats
                                from crawler import telemetry as _telemetry

                                tree_stats = collect_comment_tree_stats(comment_result.comments)
                                post.comment_stats = build_comment_stats(
                                    post_comment_count=post.comments_count,
                                    api_claimed_total=comment_result.api_claimed_total,
                                    fetched_total_count=tree_stats.total_count,
                                    fetched_top_level_count=tree_stats.top_level_count,
                                    max_depth=tree_stats.max_depth,
                                    sub_comment_completion_status=comment_result.sub_comment_completion_status,
                                    truncated_reason=comment_result.truncated_reason,
                                    pages_fetched=comment_result.pages_fetched,
                                )
                                if task_id and tree_stats.total_count > 0:
                                    _telemetry.record_event(
                                        task_id,
                                        "weibo_comment_done",
                                        delta_replies=tree_stats.total_count,
                                    )
                            except StopSignal:
                                raise  # 停止信号向上传播
                            except Exception as e:
                                logger.warning(f"抓取评论失败 mid={post.mid}: {e}")
                        all_posts_dicts.append(post.to_dict())

                # 评论抓取使用独立标签页，不影响搜索 tab，无需导航回搜索域名

                logger.info(
                    f"微博搜索第 {page} 页完成，"
                    f"本页 {len(posts)} 条，累计 {len(all_posts_dicts)} 条"
                )
                # 页面成功完成时发送心跳（含本页新增推文数）
                from crawler import telemetry as _telemetry
                _telemetry.record_event(
                    task_id,
                    "weibo_page_done",
                    page=page,
                    delta_tweets=len(posts),
                    meta={"total": len(all_posts_dicts)},
                )

                # 实时上报进度给前端（合并父级已累积数据，确保前端看到的是全任务数据）
                combined = (_parent_accumulated or []) + all_posts_dicts
                if task_id:
                    update_task_phase(
                        task_id,
                        f"微博搜索第 {page} 页完成，累计 {len(combined)} 条"
                    )
                    update_preview_tweets(
                        task_id,
                        current_page=page,
                        tweets_for_preview=combined,
                    )

                # 保存检查点
                if task_id and _parent_accumulated is None:
                    save_checkpoint(
                        task_id,
                        build_page_checkpoint(
                            keyword=keyword,
                            next_page=page + 1,
                            posts=all_posts_dicts,
                            start_date=start_date,
                            end_date=end_date,
                        ),
                    )

                if not has_next:
                    break

                # ── 翻页间隔 ──────────────────────────────────────────────
                # 不使用 jittered_sleep（其自适应等待 crawler_page_interval_max=6s
                # 会将微博专用的 12s 间隔截断为 6s）。直接用 interruptible_sleep + 手动抖动。
                _warmup_pages = 5  # 前 N 页使用加长间隔
                if page <= _warmup_pages:
                    # 预热阶段：1.2~1.5 倍间隔，模拟真人首次浏览
                    actual_interval = page_interval * random.uniform(1.2, 1.5)
                else:
                    # 正常阶段：±20% 抖动
                    actual_interval = page_interval * random.uniform(0.8, 1.2)
                logger.debug("微博翻页间隔: page=%d, interval=%.1fs", page, actual_interval)
                interruptible_sleep(max(3.0, actual_interval), task_id=task_id)

        except StopSignal:
            logger.info(f"收到停止信号，微博搜索终止 task_id={task_id}")

    finally:
        # ── Pipeline 收尾：等待 comment worker 耗尽队列 ───────────────
        if _comment_pipeline is not None and _comment_pipeline._comment_thread is not None:
            try:
                _comment_pipeline.finish_search()
                _comment_pipeline.join()
                # 将 pipeline 中已完成的评论合并回 all_posts_dicts
                for i, post_dict in enumerate(all_posts_dicts):
                    mid = str(post_dict.get("mid") or post_dict.get("id") or "")
                    if mid and mid in _comment_pipeline.result_map:
                        all_posts_dicts[i] = _comment_pipeline.result_map[mid]
                logger.info(
                    f"[WeiboCommentPipeline] 搜索+评论全部完成，"
                    f"result_map={len(_comment_pipeline.result_map)} 条"
                )
            except Exception as pipeline_cleanup_err:
                logger.error(f"[WeiboCommentPipeline] 收尾异常: {pipeline_cleanup_err}")

        # 仅最外层调用负责关闭搜索 tab，分段子调用复用当前 tab。
        if owns_tab and tab is not None:
            _close_tab_safe(tab, label="微博搜索 owns_tab 最终关闭")

    return WeiboSearchResult(posts=all_posts_dicts, resumed=resumed)
