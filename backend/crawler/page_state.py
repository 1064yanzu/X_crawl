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

# 强登录拦截标记：仅当页面主体出现这些明确的拦截性提示时才判定 login_required
# 注意：不要使用 "log in" / "sign in" 这类过于宽泛的词——
# X 的正常页面顶栏始终包含 "Log in" / "Sign in" 按钮文字，会导致误判
_LOGIN_MARKERS_STRONG = [
    "log in to x",
    "sign in to x",
    "sign in to twitter",
    "log in to twitter",
    "you need to log in",
    "you must be logged in",
    "please log in",
    "please sign in",
    "create an account",          # X 的登录拦截弹窗常见文案
    "don\u2019t miss what\u2019s happening",  # X 登录弹窗经典文案
    "don't miss what's happening", # 同上 ASCII 版
    "see what\u2019s happening",
    "join x today",
    "join twitter today",
    "登录以继续",
    "请登录",
    "需要登录",
    "登录后查看",
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


# JS 未执行空壳页检测的可见文本长度阈值
# X.com 是纯 SPA，正常渲染后可见文本至少几百字符；
# 若去掉 noscript/script/style 后文本极短，说明 JS 根本没执行
_JS_NOT_EXECUTED_TEXT_THRESHOLD = 80


def _is_js_not_executed(tab, visible_text: str) -> bool:
    """检测页面是否为 JS 未执行的空壳页。

    X.com HTML 始终包含 <noscript>JavaScript is not available.</noscript>，
    正常情况下 JS 执行后会渲染 SPA 内容，noscript 不可见。
    但如果 JS 未执行（网络问题、CDN 拦截、加载超时等），
    页面将只剩 noscript 降级文本，表现为可见内容几乎为空。
    """
    if len(visible_text) > _JS_NOT_EXECUTED_TEXT_THRESHOLD:
        return False
    try:
        raw_html = (tab.html or "").lower()
        return "javascript is not available" in raw_html
    except Exception:
        return False


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

    if any(marker in text for marker in _LOGIN_MARKERS_STRONG):
        return PageState.LOGIN_REQUIRED, "命中登录提示特征"

    # JS 未执行空壳页检测：HTML 包含 noscript 降级文本但 SPA 未渲染
    if _is_js_not_executed(tab, text):
        return PageState.TRANSIENT_ERROR, "JS 未执行，页面为 noscript 空壳页"

    return PageState.OK, "页面状态正常"


def is_error_like_state(state: PageState) -> bool:
    return state in {PageState.TRANSIENT_ERROR, PageState.RATE_LIMITED}


# ═══════════════════════════════════════════════════════════════════
#  搜索无结果检测
# ═══════════════════════════════════════════════════════════════════

_NO_RESULTS_MARKERS = [
    "no results for",           # 英文 "No results for ..."
    "没有搜索结果",
    "没有找到结果",
    "未找到结果",
]


def detect_no_results(tab) -> bool:
    """检测 X 搜索页面是否显示 "No results for ..." 无结果提示。

    当某个时间段搜索无结果时，X 前端直接渲染 "No results for ..." 页面，
    可能不会触发 SearchTimeline GraphQL 请求。
    爬虫应识别此情况并立即跳到下一个时间段，而非等待数据包超时。
    """
    text = _normalize_visible_text(tab)
    return any(marker in text for marker in _NO_RESULTS_MARKERS)


# ═══════════════════════════════════════════════════════════════════
#  X 错误页 Retry 按钮检测与点击
# ═══════════════════════════════════════════════════════════════════

# X 错误页的 Retry 按钮选择器（按优先级排列）
_RETRY_BUTTON_SELECTORS = [
    # 最精准：data-testid 标记
    '[data-testid="error-detail"] button',
    '[data-testid="errorButton"]',
    # 兜底：按钮文字匹配
    'button:contains("Retry")',
    'button:contains("Try again")',
    'button:contains("重试")',
]

# Retry 按钮存在的页面文本特征（避免在正常页面上误触）
_RETRY_PAGE_MARKERS = [
    "something went wrong",
    "try again",
    "发生错误",
    "出错了",
]

import logging as _logging
_retry_logger = _logging.getLogger(__name__)


def click_retry_button_if_present(tab) -> bool:
    """
    检测 X 页面是否出现错误页的 Retry 按钮，若有则点击并返回 True。

    X 的 "Something went wrong. Try again." 错误页面会出现一个 Retry 按钮，
    点击后可触发重新加载内容，而无需刷新整个页面。

    Returns:
        True  = 检测到 Retry 按钮并点击了
        False = 未检测到（页面正常，或非错误页）
    """
    try:
        text = _normalize_visible_text(tab)
        # 仅在有错误页特征时才尝试查找按钮，避免误触
        if not any(marker in text for marker in _RETRY_PAGE_MARKERS):
            return False

        for selector in _RETRY_BUTTON_SELECTORS:
            try:
                # DrissionPage 支持 CSS 选择器；:contains 是其扩展语法
                btn = tab.ele(f"css:{selector}", timeout=1.0)
                if btn:
                    _retry_logger.info(f"检测到 X 错误页 Retry 按钮（selector={selector!r}），正在点击...")
                    btn.click()
                    return True
            except Exception:
                continue

        # 兜底：遍历所有按钮文字
        try:
            buttons = tab.eles("tag:button")
            for btn in buttons:
                try:
                    btn_text = (btn.text or "").strip().lower()
                    if btn_text in {"retry", "try again", "重试", "再试一次"}:
                        _retry_logger.info(f"检测到 X 错误页 Retry 按钮（text={btn_text!r}），正在点击...")
                        btn.click()
                        return True
                except Exception:
                    continue
        except Exception:
            pass

    except Exception as e:
        _retry_logger.debug(f"Retry 按钮检测异常（忽略）: {e}")

    return False
