"""
登录状态验证模块
通过检查 X/Twitter Cookie 判断是否已登录

改动（v2）：
- 修复 tab.cookies(as_dict=True) 不支持关键字参数的问题（DrissionPage ≥ 4.x 已移除该参数）
- 新增 inject_cookies()：在访问 X 前先注入持久化 Cookie
- ensure_login() 成功后自动回写最新 Cookie 以刷新过期时间

改动（v3）：
- 新增 inject_account_cookies()：将 AccountEntry 的 cookies 注入 tab
- 新增 ensure_login_with_pool()：注入指定账号 cookies 并验证登录状态

改动（v4）：
- 修复 Cookie 注入时缺少 secure/httpOnly 属性导致登录失败的 BUG
- 注入前自动确保在 x.com 域下
- 增加调试日志输出实际检测到的 Cookie 名称
"""
import logging
import time
from DrissionPage._pages.chromium_tab import ChromiumTab
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crawler.account_pool import AccountEntry

from crawler.cookie_manager import (
    inject_cookies_to_tab,
    capture_cookies_from_tab,
    _build_cookie_dict,
)

logger = logging.getLogger(__name__)

X_HOME_URL = "https://x.com/home"
X_BASE_URL = "https://x.com"

# X 登录必需的两个 Cookie
_REQUIRED_COOKIES = {"auth_token", "twid"}


def _get_cookie_dict(tab: ChromiumTab) -> dict[str, str]:
    """
    安全地获取当前 tab 的所有 Cookie，返回 {name: value} 字典。
    兼容 DrissionPage 各版本（不使用 as_dict 参数）。
    """
    try:
        raw = tab.cookies()  # ≥ 4.x 返回 list[dict] 或 CookieJar
        if isinstance(raw, list):
            return {c.get("name", ""): c.get("value", "") for c in raw if c.get("name")}
        # 兼容旧版本返回字典的情况
        if isinstance(raw, dict):
            return raw
        # 兜底：尝试转为字典
        return {c.name: c.value for c in raw}
    except Exception as e:
        logger.error(f"读取 Cookie 失败: {e}")
        return {}


def check_login(tab: ChromiumTab) -> bool:
    """
    检查当前 tab 是否已登录 X
    通过检查 Cookie 中是否存在 auth_token 和 twid 判断

    Args:
        tab: DrissionPage ChromiumTab 对象

    Returns:
        True 表示已登录，False 表示未登录
    """
    cookies = _get_cookie_dict(tab)
    logged_in = all(cookies.get(key) for key in _REQUIRED_COOKIES)

    # 调试日志：输出当前检测到的所有 Cookie 名称，便于排查
    logger.debug(
        f"当前页面 Cookie 名称: {sorted(cookies.keys())}\n"
        f"  当前 URL: {tab.url}\n"
        f"  auth_token={'***…' if cookies.get('auth_token') else '缺失'}, "
        f"twid={'***…' if cookies.get('twid') else '缺失'}"
    )

    if logged_in:
        logger.info("X 登录状态验证通过")
    else:
        missing = [k for k in _REQUIRED_COOKIES if not cookies.get(k)]
        logger.warning(
            f"未检测到 X 登录凭证（缺少: {missing}）。"
            "可在设置页手动录入 Cookie 或使用已登录的 Chrome。"
        )
    return logged_in


def ensure_login(tab: ChromiumTab) -> bool:
    """
    确保 tab 已经登录 X。
    流程：
      1. 注入持久化 Cookie（若有）；注入前自动确保在 x.com 域下
      2. 等待浏览器处理 Cookie
      3. 刷新页面让 Cookie 生效
      4. 检测登录状态
      5. 若已登录，回写最新 Cookie（刷新持久化）

    Args:
        tab: DrissionPage ChromiumTab 对象

    Returns:
        True 表示已登录，False 表示仍未登录
    """
    # Step 1: 注入持久化 Cookie（inject_cookies_to_tab 内部会自动导航到 x.com）
    injected = inject_cookies_to_tab(tab)
    if injected > 0:
        logger.info(f"已注入 {injected} 条持久化 Cookie，即将刷新页面...")

    # Step 2: 等待浏览器处理注入的 Cookie
    if injected > 0:
        time.sleep(1.0)

    # Step 3: 刷新页面让 Cookie 生效
    try:
        current_url = tab.url or ""
        if "x.com" not in current_url:
            tab.get(X_BASE_URL + "/", timeout=30)
        else:
            # 已在 x.com，刷新以让注入的 Cookie 生效
            tab.get(X_BASE_URL + "/", timeout=30)
    except Exception as e:
        logger.warning(f"刷新页面失败: {e}")

    # Step 4: 等待页面完全加载
    time.sleep(2.0)

    # Step 5: 检测登录状态
    logged_in = check_login(tab)

    # Step 6: 登录成功后回写最新 Cookie（更新持久化，防止过期）
    if logged_in:
        try:
            capture_cookies_from_tab(tab)
        except Exception as e:
            logger.warning(f"回写 Cookie 失败（不影响爬取）: {e}")

    return logged_in


# ─── 账号池辅助函数 ────────────────────────────────────────────────────────

def inject_account_cookies(tab: ChromiumTab, account: "AccountEntry") -> int:
    """
    将 AccountEntry 的 cookies 注入 tab，返回注入数量。
    复用 cookie_manager 的底层注入逻辑，但 cookies 来源是 account.cookies。
    """
    if not account.cookies:
        logger.debug(f"账号 {account.alias!r} 无 Cookie，跳过注入")
        return 0

    # 确保在 x.com 域下
    try:
        current_url = tab.url or ""
        if "x.com" not in current_url and "twitter.com" not in current_url:
            tab.get("https://x.com", timeout=15)
    except Exception as e:
        logger.warning(f"导航到 x.com 失败（将继续尝试注入）: {e}")

    injected = 0
    for c in account.cookies:
        name = c.get("name")
        if not name:
            continue
        try:
            cookie_dict = _build_cookie_dict(c)
            tab.set.cookies(cookie_dict)
            injected += 1
        except Exception as e:
            logger.warning(f"注入账号 {account.alias!r} Cookie {name} 失败: {e}")

    logger.info(f"账号 {account.alias!r}：已注入 {injected} 条 Cookie")
    return injected


def ensure_login_with_pool(tab: ChromiumTab, account: "AccountEntry") -> bool:
    """
    注入指定账号 cookies 并验证登录状态。

    流程：
      1. inject_account_cookies(tab, account)
      2. 导航到 x.com（如当前不在 x.com）
      3. check_login(tab) → 验证 auth_token + twid
      4. 成功则 mark_account_used；失败则 mark_account_invalid

    Returns:
        True 表示登录成功
    """
    from crawler.account_pool import get_pool

    # Step 1: 注入账号 Cookie
    injected = inject_account_cookies(tab, account)
    if injected > 0:
        logger.info(f"账号 {account.alias!r}：注入 {injected} 条 Cookie，即将刷新页面...")

    # Step 2: 等待浏览器处理注入的 Cookie
    if injected > 0:
        time.sleep(1.0)

    # Step 3: 访问/刷新 x.com
    try:
        current_url = tab.url or ""
        if "x.com" not in current_url:
            tab.get(X_BASE_URL + "/", timeout=30)
        else:
            tab.get(X_BASE_URL + "/", timeout=30)
    except Exception as e:
        logger.warning(f"刷新页面失败: {e}")

    # Step 4: 等待页面完全加载
    time.sleep(2.0)

    # Step 5: 检测登录状态
    logged_in = check_login(tab)

    # Step 6: 更新账号状态
    pool = get_pool()
    if logged_in:
        pool.mark_account_used(account.account_id)
        pool.mark_account_validated(account.account_id)
        logger.info(f"账号 {account.alias!r} 登录验证通过")
    else:
        pool.mark_account_invalid(account.account_id)
        logger.warning(f"账号 {account.alias!r} 登录验证失败，已标记无效")

    return logged_in
