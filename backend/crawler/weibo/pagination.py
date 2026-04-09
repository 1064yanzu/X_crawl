"""
微博搜索翻页模块（V4）。

翻页策略：提取"下一页"链接的 href，然后用 tab.get(href) 导航。
这既保留了"来自当前页面的导航"的自然性（Referer/Cookie 上下文），
又完全由 DrissionPage 内部管理 CDP 生命周期，不会出现 CDP 管道拥堵。

不再使用：
- ele.click() 后手动轮询（会导致 CDP 管道拥堵）
- run_js()（CDP 上下文销毁时超时）
- wait.load_start()（页面已完成时会死等下一个加载事件）
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def click_next_page(
    tab,
    *,
    expected_page: int,
    timeout: float = 15.0,
) -> tuple[Optional[str], Optional[str]]:
    """
    通过提取"下一页"链接并用 tab.get() 导航到下一页。

    这是最安全的翻页方式：
    1. 提取 href（不触发导航，CDP 操作轻量）
    2. tab.get(href)（DrissionPage 完全管理 CDP 生命周期）
    3. tab.html（加载完成后读取，不需要手动轮询）

    Args:
        tab: DrissionPage 的 ChromiumTab 实例
        expected_page: 期望的目标页码
        timeout: tab.get() 的加载超时时间

    Returns:
        (html, error) — 成功时 error 为 None，失败时 html 为 None
    """
    from .http_418_guard import detect_weibo_http_418

    # ── 1. 找到"下一页"链接并提取 href ─────────────────────────────
    next_href = None

    # 方式 1：CSS class
    try:
        next_btn = tab.ele("css:a.next", timeout=5)
        if next_btn:
            next_href = next_btn.attr("href")
    except Exception as e:
        logger.debug("查找 a.next 失败: %s", e)

    # 方式 2：文字匹配
    if not next_href:
        try:
            next_btn = tab.ele("text:下一页", timeout=3)
            if next_btn:
                next_href = next_btn.attr("href")
        except Exception as e:
            logger.debug("查找 '下一页' 文字链接失败: %s", e)

    if not next_href:
        return None, "页面上未找到'下一页'链接或其 href 属性"

    # 补全 URL（href 可能是相对路径）
    if next_href.startswith("//"):
        next_href = "https:" + next_href
    elif next_href.startswith("/"):
        next_href = "https://s.weibo.com" + next_href

    logger.debug("下一页链接: %s", next_href[:100])

    # ── 2. 用 tab.get() 导航（DrissionPage 完全管理 CDP 生命周期）──
    try:
        success = tab.get(next_href, retry=1, interval=2, timeout=timeout)
    except Exception as e:
        return None, f"tab.get() 导航失败: {e}"

    if not success:
        return None, "tab.get() 导航返回 False（页面加载失败或超时）"

    # ── 3. 读取并验证页面 ─────────────────────────────────────────
    try:
        current_url = tab.url or ""
    except Exception as e:
        return None, f"CDP_DEAD:导航后读取 tab.url 失败: {e}"

    # 反爬检测
    if "passport.weibo.com" in current_url:
        return None, "反爬拦截: 被重定向到登录页"
    if "security.weibo.com" in current_url:
        return None, "反爬拦截: 触发安全验证页面"

    try:
        html = tab.html or ""
    except Exception as e:
        return None, f"CDP_DEAD:导航后读取 tab.html 失败: {e}"

    if len(html) < 2000:
        return None, "页面 HTML 过短，疑似未正确加载"

    # 内容级反爬检测
    if "请登录" in html:
        return None, "反爬拦截: 页面要求登录"

    try:
        if detect_weibo_http_418(tab):
            return None, "微博 HTTP 418 错误页"
    except Exception:
        pass

    logger.info("通过'下一页'链接成功导航到第 %d 页", expected_page)
    return html, None
