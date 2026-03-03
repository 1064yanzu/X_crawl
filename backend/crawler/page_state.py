"""页面状态检测：用于区分正常页、临时错误页和风控挑战页。"""
from __future__ import annotations

from enum import Enum
import re


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
    # 注意: 不要包含 "javascript is not available"
    # X 的 HTML 始终包含 <noscript><h1>JavaScript is not available.</h1></noscript>
    # 这是正常的 noscript 降级标签，不是错误页面标志
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


def _normalize_visible_text(tab) -> str:
    """提取可见文本，避免脚本/样式/noscript中的误判。"""
    try:
        html = tab.html or ""
        # 分别去掉 script/style/noscript 块（不使用反向引用，更可靠）
        html = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", html)
        html = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", html)
        html = re.sub(r"(?is)<noscript\b[^>]*>.*?</noscript>", " ", html)
        # 再粗略去标签，保留可见文本
        text = re.sub(r"(?is)<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip().lower()
        # 额外移除 X 页面常见的 noscript 残留文案（以防正则未覆盖）
        text = text.replace("javascript is not available.", "")
        text = text.replace("javascript is not available", "")
        return text[:120_000]
    except Exception:
        return ""


def _normalize_url(tab) -> str:
    try:
        return (tab.url or "").lower()
    except Exception:
        return ""


def detect_page_state(tab) -> tuple[PageState, str]:
    """基于 URL + 页面可见文本特征判断当前页面状态。"""
    text = _normalize_visible_text(tab)
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
