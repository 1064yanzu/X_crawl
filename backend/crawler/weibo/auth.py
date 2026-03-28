"""
微博登录验证：注入 Cookie 并检测登录状态。

关键修复：
1. 必须先导航到目标域名，再注入 Cookie，否则 browser 不会接受 .weibo.com 域的 Cookie
2. 支持为 s.weibo.com（搜索）和 weibo.com（评论API）两个域名注入 Cookie
3. 为搜索页单独准备 Cookie，确保 s.weibo.com 上的 Cookie 可用
4. 支持按指定账号注入 Cookie，避免多账号并发时 Cookie 互相覆盖
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _get_account_cookies(account_cookies: Optional[list[dict]] = None) -> list[dict]:
    """
    获取要注入的 Cookie 列表。
    优先使用传入的账号 Cookie，否则从账号池取第一个可用账号，
    最后回退到全局 Cookie 文件。
    """
    if account_cookies:
        return account_cookies

    # 尝试从微博账号池取第一个可用账号
    try:
        from .account_pool import get_weibo_pool
        pool = get_weibo_pool()
        account = pool.pick_next_account()
        if account and account.cookies:
            logger.debug(f"使用微博账号 {account.alias!r} 的 Cookie")
            return account.cookies
    except Exception:
        pass

    # 回退到全局 Cookie 文件
    from .cookie_manager import load_cookies
    return load_cookies()


def ensure_weibo_login(tab, account_cookies: Optional[list[dict]] = None) -> bool:
    """
    注入 Cookie 并验证微博登录状态。

    Args:
        tab: 浏览器 tab
        account_cookies: 指定账号的 Cookie 列表。为 None 时自动从账号池或全局文件获取。

    流程：
    1. 先导航到 weibo.com（让浏览器处于 .weibo.com 域下）
    2. 注入 Cookie
    3. 刷新页面验证登录状态

    返回 True 代表已登录，False 代表需要手动登录。
    """
    from .cookie_manager import inject_cookies_to_tab, has_weibo_login

    cookies = _get_account_cookies(account_cookies)
    if not cookies:
        return False

    # 先导航到 weibo.com，让浏览器处于正确域名下，Cookie 才能被正确设置
    try:
        tab.get("https://weibo.com", timeout=15)
        time.sleep(1)
    except Exception as e:
        logger.warning(f"导航到 weibo.com 失败: {e}")

    # 在正确域名下注入 Cookie
    inject_cookies_to_tab(tab, cookies)
    logger.info(f"已注入 {len(cookies)} 条微博 Cookie")

    # 刷新页面让 Cookie 生效
    try:
        tab.get("https://weibo.com", timeout=15)
        time.sleep(2)
    except Exception as e:
        logger.warning(f"刷新 weibo.com 失败: {e}")
        return False

    # 检查是否已登录：页面 URL 不跳转到 passport.weibo.com 且有 SUB cookie
    current_url = tab.url
    if "passport.weibo.com" in current_url:
        logger.warning("Cookie 注入后仍跳转到登录页，Cookie 可能已过期")
        return False

    logged_in = has_weibo_login(cookies)
    if logged_in:
        logger.info("微博登录验证成功")
    return logged_in


def ensure_search_cookies(tab, account_cookies: Optional[list[dict]] = None) -> None:
    """
    为 s.weibo.com 搜索页准备 Cookie。

    Args:
        tab: 浏览器 tab
        account_cookies: 指定账号的 Cookie 列表。为 None 时自动从账号池或全局文件获取。

    s.weibo.com 与 weibo.com 共享 .weibo.com 域的 Cookie，
    但某些 Cookie（如 PC_TOKEN）只在访问 s.weibo.com 时由服务端下发。
    此方法先导航到 s.weibo.com，触发服务端 Set-Cookie，确保搜索请求不会被拦截。
    """
    from .cookie_manager import inject_cookies_to_tab

    cookies = _get_account_cookies(account_cookies)
    if not cookies:
        return

    try:
        # 先导航到 s.weibo.com 触发域名下的 Cookie 设置
        tab.get("https://s.weibo.com", timeout=15)
        time.sleep(1)
        # 在 s.weibo.com 域名下再次注入 Cookie，确保生效
        inject_cookies_to_tab(tab, cookies)
        time.sleep(1)
        logger.info("s.weibo.com 搜索 Cookie 准备完成")
    except Exception as e:
        logger.warning(f"准备搜索 Cookie 失败: {e}")
