"""页面状态检测：用于区分正常页、临时错误页和风控挑战页。"""
from __future__ import annotations

from enum import Enum


class PageState(str, Enum):
    OK = "ok"
    TRANSIENT_ERROR = "transient_error"
    CHALLENGE = "challenge"
    LOGIN_REQUIRED = "login_required"
    RATE_LIMITED = "rate_limited"


_TRANSIENT_ERROR_MARKERS = [
    "something went wrong",
    "try reloading",
    "hmm...this page doesn",
    "hmm, this page doesn",
    "发生错误",
    "出错了",
]

_CHALLENGE_MARKERS = [
    "verify you are human",
    "confirm you are human",
    "security challenge",
    "complete the security check",
    "captcha",
    "robot check",
    "验证你是人类",
    "安全验证",
]

_RATE_LIMIT_MARKERS = [
    "rate limit exceeded",
    "too many requests",
    "try again later",
    "请求过于频繁",
    "访问过于频繁",
]

_LOGIN_MARKERS = [
    "log in",
    "sign in",
    "登录",
    "登入",
]


def _normalize_html(tab) -> str:
    try:
        html = tab.html or ""
        return html.lower()[:120_000]
    except Exception:
        return ""


def _normalize_url(tab) -> str:
    try:
        return (tab.url or "").lower()
    except Exception:
        return ""


def detect_page_state(tab) -> tuple[PageState, str]:
    """基于 URL + 页面文本特征判断当前页面状态。"""
    text = _normalize_html(tab)
    url = _normalize_url(tab)

    if "/i/flow/login" in url or "/login" in url:
        return PageState.LOGIN_REQUIRED, "命中登录 URL"

    if any(marker in text for marker in _CHALLENGE_MARKERS):
        return PageState.CHALLENGE, "命中风控挑战特征"

    if any(marker in text for marker in _RATE_LIMIT_MARKERS):
        return PageState.RATE_LIMITED, "命中限流特征"

    if any(marker in text for marker in _TRANSIENT_ERROR_MARKERS):
        return PageState.TRANSIENT_ERROR, "命中临时错误页特征"

    if any(marker in text for marker in _LOGIN_MARKERS) and "x.com" in url and "home" not in url:
        return PageState.LOGIN_REQUIRED, "命中登录提示特征"

    return PageState.OK, "页面状态正常"


def is_error_like_state(state: PageState) -> bool:
    return state in {PageState.TRANSIENT_ERROR, PageState.RATE_LIMITED}
