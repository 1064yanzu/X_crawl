"""
微博搜索翻页模块（V5）。

翻页策略：提取"下一页"链接的 href，然后用 tab.get(href) 导航。

关键处理：
- tab.get() 超时后不放弃——页面很可能已加载好，只是 DrissionPage 内部的
  Page.stopLoading 确认信号没通过拥堵的 CDP 管道。此时尝试读取 tab.html。
- 使用 eager 加载模式，DOM 就绪即完成（不等资源加载），减少 CDP 管道压力。
"""
from __future__ import annotations

import logging
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

    try:
        next_btn = tab.ele("css:a.next", timeout=5)
        if next_btn:
            next_href = next_btn.attr("href")
    except Exception as e:
        logger.debug("查找 a.next 失败: %s", e)

    if not next_href:
        try:
            next_btn = tab.ele("text:下一页", timeout=3)
            if next_btn:
                next_href = next_btn.attr("href")
        except Exception as e:
            logger.debug("查找 '下一页' 文字链接失败: %s", e)

    if not next_href:
        return None, "页面上未找到'下一页'链接或其 href 属性"

    # 补全 URL
    if next_href.startswith("//"):
        next_href = "https:" + next_href
    elif next_href.startswith("/"):
        next_href = "https://s.weibo.com" + next_href

    logger.debug("下一页链接: %s", next_href[:100])



    # ── 3. tab.get() 导航 ────────────────────────────────────────
    nav_success = False
    nav_error = None
    try:
        nav_success = tab.get(next_href, retry=0, timeout=timeout)
    except Exception as e:
        nav_error = str(e)
        logger.debug("tab.get() 异常: %s", nav_error[:120])



    # ── 5. 验证页面（即使 tab.get 超时，页面可能已加载好）──────────
    # tab.get() 超时通常是 Page.stopLoading CDP 命令拥堵，
    # 不代表页面没加载——浏览器截图能看到页面内容。
    html = _try_read_page(tab)

    if html:
        # 反爬检测
        anti_crawl = _check_anti_crawl(tab, html)
        if anti_crawl:
            return None, anti_crawl

        try:
            if detect_weibo_http_418(tab):
                return None, "微博 HTTP 418 错误页"
        except Exception:
            pass

        if nav_success:
            logger.info("通过'下一页'链接成功导航到第 %d 页", expected_page)
        else:
            logger.info(
                "tab.get() 报告失败但页面实际已加载，恢复第 %d 页成功",
                expected_page,
            )
        return html, None

    # 页面确实没加载好
    error_msg = f"tab.get() 导航失败: {nav_error}" if nav_error else "tab.get() 返回 False 且页面未加载"
    return None, error_msg


def _try_read_page(tab) -> Optional[str]:
    """尝试读取当前页面 HTML，失败返回 None。"""
    try:
        url = tab.url or ""
        if "s.weibo.com" not in url:
            return None
        html = tab.html or ""
        if len(html) < 2000:
            return None
        return html
    except Exception:
        return None


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
