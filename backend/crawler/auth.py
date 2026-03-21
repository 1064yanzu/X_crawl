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

改动（v5）：
- 优先复用当前 profile 中已存在的登录态，再回退到 Cookie 注入
- 登录校验同时结合页面状态，区分 challenge/login_required 与普通页面
- 记录最近一次登录检查诊断信息，供任务状态与设置页展示
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from DrissionPage._pages.chromium_tab import ChromiumTab

if TYPE_CHECKING:
    from crawler.account_pool import AccountEntry

from crawler.browser import get_browser_session_info, promote_browser_for_manual_interaction
from crawler.cookie_manager import (
    inject_cookies_to_tab,
    capture_cookies_from_tab,
    _build_cookie_dict,
)
from crawler.page_state import PageState, detect_page_state

logger = logging.getLogger(__name__)

X_HOME_URL = "https://x.com/home"
X_BASE_URL = "https://x.com"

# X 登录必需的两个 Cookie
_REQUIRED_COOKIES = {"auth_token", "twid"}


def _extract_twid_uid(twid_value: str) -> str:
    """从 twid cookie 值（如 'u%3D1234' 或 'u=1234'）提取用户 ID。"""
    from urllib.parse import unquote
    decoded = unquote(twid_value)  # u%3D1234 -> u=1234
    if decoded.startswith("u="):
        return decoded[2:]
    return decoded


def _get_account_twid(account: "AccountEntry") -> str:
    """从 AccountEntry 的 cookies 中提取 twid 用户 ID。"""
    for c in (account.cookies or []):
        name = c.get("name", "") if isinstance(c, dict) else getattr(c, "name", "")
        value = c.get("value", "") if isinstance(c, dict) else getattr(c, "value", "")
        if name == "twid" and value:
            return _extract_twid_uid(value)
    return ""


@dataclass
class LoginCheckResult:
    ok: bool
    cookie_present: bool
    session_valid: bool
    missing_cookies: list[str] = field(default_factory=list)
    cookie_names: list[str] = field(default_factory=list)
    current_url: str = ""
    page_state: str = PageState.OK.value
    page_reason: str = ""


@dataclass
class EnsureLoginResult:
    ok: bool
    reason: str
    source: str
    injected_count: int
    check: LoginCheckResult
    session_mode: str
    effective_user_data_path: Optional[str]


_login_diagnostics: dict[str, object] = {
    "last_login_check_at": None,
    "last_login_success_at": None,
    "last_login_failure_reason": None,
    "last_page_state": None,
    "last_page_reason": None,
    "last_url": None,
    "last_missing_cookies": [],
    "last_cookie_names": [],
    "session_mode": "unknown",
    "effective_user_data_path": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_login_diagnostics() -> dict[str, object]:
    return dict(_login_diagnostics)


def _current_url(tab: ChromiumTab) -> str:
    try:
        return tab.url or ""
    except Exception:
        return ""


def _get_cookie_dict(tab: ChromiumTab) -> dict[str, str]:
    """
    安全地获取当前 tab 的所有 Cookie，返回 {name: value} 字典。
    兼容 DrissionPage 各版本（不使用 as_dict 参数）。
    """
    try:
        raw = tab.cookies()  # ≥ 4.x 返回 list[dict] 或 CookieJar
        if isinstance(raw, list):
            return {c.get("name", ""): c.get("value", "") for c in raw if c.get("name")}
        if isinstance(raw, dict):
            return raw
        return {c.name: c.value for c in raw}
    except Exception as e:
        logger.error(f"读取 Cookie 失败: {e}")
        return {}


def _detect_page_state_safe(tab: ChromiumTab) -> tuple[PageState, str]:
    try:
        return detect_page_state(tab)
    except Exception as e:
        logger.warning(f"检测页面状态失败，按 OK 兜底: {e}")
        return PageState.OK, "页面状态检测失败，已兜底为 OK"


def _session_valid_for_login(page_state: PageState) -> bool:
    return page_state not in {PageState.LOGIN_REQUIRED, PageState.CHALLENGE}


def _infer_failure_reason(check: LoginCheckResult, *, attempted_injection: bool) -> str:
    if check.page_state == PageState.CHALLENGE.value:
        return "challenge_required"
    if check.page_state == PageState.LOGIN_REQUIRED.value:
        return "cookie_injection_failed" if attempted_injection else "profile_missing_login"
    if check.missing_cookies:
        return "cookie_injection_failed" if attempted_injection else "profile_missing_login"
    return "cookie_injection_failed" if attempted_injection else "login_required"


def _record_login_result(result: EnsureLoginResult) -> None:
    now = _now_iso()
    _login_diagnostics.update({
        "last_login_check_at": now,
        "last_page_state": result.check.page_state,
        "last_page_reason": result.check.page_reason,
        "last_url": result.check.current_url,
        "last_missing_cookies": list(result.check.missing_cookies),
        "last_cookie_names": list(result.check.cookie_names),
        "session_mode": result.session_mode,
        "effective_user_data_path": result.effective_user_data_path,
    })
    if result.ok:
        _login_diagnostics["last_login_success_at"] = now
        _login_diagnostics["last_login_failure_reason"] = None
    else:
        _login_diagnostics["last_login_failure_reason"] = result.reason


def _assess_login(tab: ChromiumTab) -> LoginCheckResult:
    cookies = _get_cookie_dict(tab)
    cookie_names = sorted(cookies.keys())
    missing = sorted(k for k in _REQUIRED_COOKIES if not cookies.get(k))
    cookie_present = not missing
    page_state, page_reason = _detect_page_state_safe(tab)
    current_url = _current_url(tab)
    session_valid = _session_valid_for_login(page_state)
    ok = cookie_present and session_valid

    message = (
        f"X 登录检查 | url={current_url or '-'} | page_state={page_state.value} | "
        f"missing={missing or '[]'} | cookies={cookie_names}"
    )
    if ok:
        logger.info(f"X 登录状态验证通过 | {message}")
    else:
        logger.warning(f"X 登录状态验证失败 | {message}")

    return LoginCheckResult(
        ok=ok,
        cookie_present=cookie_present,
        session_valid=session_valid,
        missing_cookies=missing,
        cookie_names=cookie_names,
        current_url=current_url,
        page_state=page_state.value,
        page_reason=page_reason,
    )


def check_login(tab: ChromiumTab) -> bool:
    """
    检查当前 tab 是否已登录 X。
    通过关键 Cookie + 页面状态联合判断。
    """
    check = _assess_login(tab)
    session_info = get_browser_session_info()
    _record_login_result(EnsureLoginResult(
        ok=check.ok,
        reason="ok" if check.ok else _infer_failure_reason(check, attempted_injection=False),
        source="profile",
        injected_count=0,
        check=check,
        session_mode=str(session_info.get("session_mode") or "unknown"),
        effective_user_data_path=session_info.get("effective_user_data_path"),
    ))
    return check.ok


def _refresh_x_home(tab: ChromiumTab) -> None:
    try:
        current_url = _current_url(tab)
        if "x.com" not in current_url and "twitter.com" not in current_url:
            tab.get(X_BASE_URL + "/", timeout=30)
        else:
            tab.get(X_BASE_URL + "/", timeout=30)
    except Exception as e:
        logger.warning(f"刷新页面失败: {e}")


def _ensure_x_domain_context(tab: ChromiumTab) -> None:
    """在首次登录检查前确保标签页已进入 X 域，避免 about:blank 误判未登录。"""
    try:
        current_url = _current_url(tab)
        if "x.com" in current_url or "twitter.com" in current_url:
            return
        logger.info("当前标签页尚未进入 X 域，先访问 x.com/home 再校验登录状态")
        tab.get(X_HOME_URL, timeout=30)
        time.sleep(1.0)
    except Exception as e:
        logger.warning(f"建立 X 域上下文失败，将继续按当前页面校验登录: {e}")


def _finalize_login_result(
    tab: ChromiumTab,
    *,
    source: str,
    injected_count: int,
    attempted_injection: bool,
) -> EnsureLoginResult:
    session_info = get_browser_session_info()
    check = _assess_login(tab)
    result = EnsureLoginResult(
        ok=check.ok,
        reason="ok" if check.ok else _infer_failure_reason(check, attempted_injection=attempted_injection),
        source=source,
        injected_count=injected_count,
        check=check,
        session_mode=str(session_info.get("session_mode") or "unknown"),
        effective_user_data_path=session_info.get("effective_user_data_path"),
    )
    _record_login_result(result)
    if not result.ok:
        promote_browser_for_manual_interaction(tab, reason=result.reason)
    return result


def ensure_login_detailed(tab: ChromiumTab) -> EnsureLoginResult:
    """
    确保 tab 已登录 X。
    优先复用当前 profile 中已有登录态；若缺失，再尝试注入持久化 Cookie 兜底。
    注意：Cloudflare challenge 不是登录问题，Cookie 注入无法解决——直接返回失败让任务暂停。
    """
    _ensure_x_domain_context(tab)
    current = _finalize_login_result(tab, source="profile", injected_count=0, attempted_injection=False)
    if current.ok:
        try:
            capture_cookies_from_tab(tab)
        except Exception as e:
            logger.warning(f"回写 Cookie 失败（不影响爬取）: {e}")
        return current

    # Cloudflare challenge / 风控挑战：Cookie 注入无法解决，直接返回让任务暂停等用户验证
    if current.check.page_state in (PageState.CHALLENGE.value, PageState.RATE_LIMITED.value):
        logger.warning(
            f"检测到 {current.check.page_state}（非登录问题），跳过 Cookie 注入，"
            f"等待用户在浏览器中完成验证"
        )
        return current

    injected = inject_cookies_to_tab(tab)
    if injected > 0:
        logger.info(f"已注入 {injected} 条持久化 Cookie，即将刷新页面...")
        time.sleep(1.0)

    _refresh_x_home(tab)
    time.sleep(2.0)

    result = _finalize_login_result(
        tab,
        source="cookies" if injected > 0 else "profile",
        injected_count=injected,
        attempted_injection=injected > 0,
    )
    if result.ok:
        try:
            capture_cookies_from_tab(tab)
        except Exception as e:
            logger.warning(f"回写 Cookie 失败（不影响爬取）: {e}")
    return result


def ensure_login(tab: ChromiumTab) -> bool:
    return ensure_login_detailed(tab).ok


# ─── 账号池辅助函数 ────────────────────────────────────────────────────────

def inject_account_cookies(tab: ChromiumTab, account: "AccountEntry") -> int:
    """
    将 AccountEntry 的 cookies 注入 tab，返回注入数量。
    复用 cookie_manager 的底层注入逻辑，但 cookies 来源是 account.cookies。
    """
    if not account.cookies:
        logger.debug(f"账号 {account.alias!r} 无 Cookie，跳过注入")
        return 0

    try:
        current_url = _current_url(tab)
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


def ensure_login_with_pool_detailed(tab: ChromiumTab, account: "AccountEntry") -> EnsureLoginResult:
    """注入指定账号 cookies 并验证登录状态。
    注意：Cloudflare challenge 不是登录/账号问题，Cookie 注入无法解决——直接返回失败。
    """
    from crawler.account_pool import get_pool

    _ensure_x_domain_context(tab)
    current = _finalize_login_result(tab, source="account_profile", injected_count=0, attempted_injection=False)

    # ── 已有登录态时，验证当前 twid 是否匹配目标账号 ──────────────────
    need_inject = True  # 默认需要注入
    if current.ok:
        browser_cookies = _get_cookie_dict(tab)
        browser_twid_uid = _extract_twid_uid(browser_cookies.get("twid", ""))
        target_twid_uid = _get_account_twid(account)
        if target_twid_uid and browser_twid_uid and browser_twid_uid != target_twid_uid:
            logger.info(
                f"账号 {account.alias!r}：当前 profile 已登录为 uid={browser_twid_uid}，"
                f"但目标账号 uid={target_twid_uid}，需要重新注入 Cookie"
            )
            # twid 不匹配，继续走注入流程
        else:
            # 匹配或无法判断（向后兼容），直接返回
            need_inject = False
            pool = get_pool()
            pool.mark_account_used(account.account_id)
            pool.mark_account_validated(account.account_id)
            logger.info(f"账号 {account.alias!r} 登录验证通过（profile 匹配）")
            return current

    # ── Cloudflare challenge：不是账号问题，Cookie 注入无法解决 ────────
    if current.check.page_state in (PageState.CHALLENGE.value, PageState.RATE_LIMITED.value):
        # Cloudflare challenge / 风控挑战：不是账号问题，Cookie 注入无法解决
        logger.warning(
            f"账号 {account.alias!r}：检测到 {current.check.page_state}（非账号问题），"
            f"跳过 Cookie 注入，等待用户在浏览器中完成验证"
        )
        result = current
    else:
        injected = inject_account_cookies(tab, account)
        if injected > 0:
            logger.info(f"账号 {account.alias!r}：注入 {injected} 条 Cookie，即将刷新页面...")
            time.sleep(1.0)
        _refresh_x_home(tab)
        time.sleep(2.0)
        result = _finalize_login_result(
            tab,
            source="account_cookies" if injected > 0 else "account_profile",
            injected_count=injected,
            attempted_injection=injected > 0,
        )

    pool = get_pool()
    if result.ok:
        pool.mark_account_used(account.account_id)
        pool.mark_account_validated(account.account_id)
        logger.info(f"账号 {account.alias!r} 登录验证通过")
    else:
        # 以下原因不是账号本身的问题，不标记为无效：
        # - challenge_required: Cloudflare 五秒盾，浏览器环境问题
        # - cookie_injection_failed: profile 残留旧 Cookie 导致注入后验证失败，浏览器环境问题
        _non_account_reasons = {"challenge_required", "cookie_injection_failed"}
        if result.reason in _non_account_reasons:
            logger.warning(
                f"账号 {account.alias!r} 登录失败（reason={result.reason}），"
                f"但这不是账号问题，不标记为无效"
            )
        else:
            pool.mark_account_invalid(account.account_id)
            logger.warning(f"账号 {account.alias!r} 登录验证失败，已标记无效，reason={result.reason}")

    return result


def ensure_login_with_pool(tab: ChromiumTab, account: "AccountEntry") -> bool:
    return ensure_login_with_pool_detailed(tab, account).ok
