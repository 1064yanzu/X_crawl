"""
微博搜索翻页模块。

翻页策略：
- 优先点击页面上的“下一页”链接，避免把翻页退化成 `tab.get()` 直接导航。
- 点击后使用轻量轮询验证 URL 与 DOM 是否已切到目标页，尽量少走 CDP 重命令。

设计目标：
- 避免 `Page.stopLoading` / `Page.getFrameTree` 一类 `tab.get()` 相关超时。
- 更接近真实用户翻页路径，降低风控与卡死概率。
"""
from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


def click_next_page(
    tab,
    *,
    expected_page: int,
    timeout: float = 15.0,
) -> tuple[Optional[str], Optional[str]]:
    """
    通过真实点击“下一页”链接翻到目标页。

    Args:
        tab: DrissionPage 的 ChromiumTab 实例
        expected_page: 期望的目标页码
        timeout: 点击后的等待超时时间

    Returns:
        (html, error) — 成功时 error 为 None，失败时 html 为 None
    """
    from .http_418_guard import detect_weibo_http_418

    # ── 1. 找到“下一页”按钮 ────────────────────────────────────────
    next_btn = None

    try:
        next_btn = tab.ele("css:a.next", timeout=5)
    except Exception as e:
        logger.debug("查找 a.next 失败: %s", e)

    if not next_btn:
        try:
            next_btn = tab.ele("text:下一页", timeout=3)
        except Exception as e:
            logger.debug("查找 '下一页' 文字链接失败: %s", e)

    if not next_btn:
        return None, "页面上未找到'下一页'链接"

    next_href = ""
    try:
        next_href = next_btn.attr("href") or ""
    except Exception as e:
        logger.debug("读取下一页 href 失败（忽略，继续点击）: %s", e)

    if next_href.startswith("//"):
        next_href = "https:" + next_href
    elif next_href.startswith("/"):
        next_href = "https://s.weibo.com" + next_href

    if next_href:
        logger.debug("下一页链接: %s", next_href[:100])

    # ── 2. 真实点击下一页 ──────────────────────────────────────────
    try:
        next_btn.click()
    except Exception as e:
        return None, f"点击'下一页'失败: {e}"

    # ── 3. 轮询验证页面是否已切到目标页 ────────────────────────────
    deadline = time.monotonic() + max(3.0, timeout)
    last_error = "点击后页面尚未就绪"
    time.sleep(1.2)
    while time.monotonic() < deadline:
        html, read_error = _try_read_page(tab)
        if html:
            current_url = _safe_get_url(tab)
            if _page_matches(current_url, expected_page, next_href=next_href):
                anti_crawl = _check_anti_crawl(tab, html)
                if anti_crawl:
                    return None, anti_crawl

                try:
                    if detect_weibo_http_418(tab):
                        return None, "微博 HTTP 418 错误页"
                except Exception:
                    pass

                logger.info("通过点击'下一页'成功导航到第 %d 页", expected_page)
                return html, None

            last_error = (
                f"页码尚未切换到目标页: current_url={current_url or '<empty>'}, "
                f"expected_page={expected_page}"
            )
        else:
            last_error = read_error or last_error
        time.sleep(0.5)

    if "超时" in last_error or "timeout" in last_error.lower():
        return None, f"[CDP_DEAD] 点击翻页后读取验证失败: {last_error}"
    return None, f"点击翻页后页面未就绪: {last_error}"


def _try_read_page(tab) -> tuple[Optional[str], Optional[str]]:
    """尝试读取当前页面 HTML，返回值: (html, error_msg)"""
    try:
        url = tab.url or ""
        if "s.weibo.com" not in url:
            return None, "非搜索页面URL"
        html = tab.html or ""
        if len(html) < 2000:
            return None, "页面HTML太短"
        return html, None
    except Exception as e:
        return None, f"读取 tab 状态失败: {e}"


def _safe_get_url(tab) -> str:
    try:
        return tab.url or ""
    except Exception:
        return ""


def _page_matches(current_url: str, expected_page: int, *, next_href: str = "") -> bool:
    for candidate in (current_url, next_href):
        if not candidate:
            continue
        try:
            page = parse_qs(urlparse(candidate).query).get("page", [None])[0]
            if str(page or "") == str(expected_page):
                return True
        except Exception:
            continue
    return False


def _check_anti_crawl(tab, html: str) -> Optional[str]:
    """检查反爬拦截，返回原因字符串或 None。"""
    try:
        url = tab.url or ""
    except Exception:
        url = ""
    if "passport.weibo.com" in url:
        return "反爬拦截: 被重定向到登录页"
    if "security.weibo.com" in url:
        return "反爬拦截: 触发安全验证页面"
    if "请登录" in html:
        return "反爬拦截: 页面要求登录"
    return None
