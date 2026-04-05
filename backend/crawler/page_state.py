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
    SPLASH = "splash"   # X 黑屏启动画面（JS 执行中但 SPA 尚未渲染内容）


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

# Cloudflare 专属特征词（比一般 challenge 更精准）
_CLOUDFLARE_MARKERS = [
    "checking if the site connection is secure",
    "checking your browser",
    "please wait…",            # Cloudflare 常见期待文案
    "enable javascript and cookies to continue",
    "cloudflare",
    "正在验证",                  # 有时中文 CF 页面会显示
    "verification required",
    "ddos protection by",
    "attention required",
    "ray id",                   # Cloudflare 错误页常见的跟踪 ID
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


def _is_tweet_detail_with_content(tab, url: str, text: str) -> bool:
    """判断当前是否为已加载主体内容的推文/搜索详情页。

    推文详情页和搜索页上的评论区或局部组件可能显示"出错了/Something went wrong"，
    但页面主体（推文正文、用户名、搜索结果）已正常加载。
    此函数通过 URL 模式 + 页面内容长度来识别这种场景，防止误判为全页错误。
    """
    # 推文详情页: /user/status/xxx
    # 搜索结果页: /search?q=xxx
    is_detail_url = "/status/" in url or "/search" in url
    if not is_detail_url:
        return False
    # 全页错误通常文本极短（<500字符），只有错误提示和几个按钮
    # 正常的推文详情页/搜索页有推文内容、用户名、时间戳等，文本远超 500 字符
    return len(text) > 500


# JS 未执行空壳页检测的可见文本长度阈值
# X.com 是纯 SPA，正常渲染后可见文本至少几百字符；
# 若去掉 noscript/script/style 后文本极短，说明 JS 根本没执行
_JS_NOT_EXECUTED_TEXT_THRESHOLD = 80

# Splash 状态阈值：可见文本略多一点但仍然极少，JS 已执行但 SPA 还在加载
# 典型表现：黑屏+X logo，HTML 里有少量框架代码但没有渲染内容
_SPLASH_TEXT_THRESHOLD = 200


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


def _is_splash_loading(tab, visible_text: str) -> bool:
    """检测页面是否处于 X 启动黑屏状态（SPA 正在加载但尚未渲染内容）。

    X.com 打开时会先显示黑屏+X logo 的启动画面（splash screen），
    此时 JS 已经执行，noscript 降级文本不存在，
    但 SPA 还没渲染出任何可见内容。
    这种状态需要等待 JS 完成渲染，而不是立即报告错误。

    特征：
    1. 可见文本极少（<= _SPLASH_TEXT_THRESHOLD）
    2. 不是 noscript 空壳页（JS 已执行）
    3. 当前 URL 是 x.com 域名
    4. HTML 中存在 React/SPA 挂载点（#react-root 或 #layers）
    """
    if len(visible_text) > _SPLASH_TEXT_THRESHOLD:
        return False
    # noscript 空壳页单独处理，不算 splash
    if _is_js_not_executed(tab, visible_text):
        return False
    try:
        url = _normalize_url(tab)
        if "x.com" not in url and "twitter.com" not in url:
            return False
        raw_html = (tab.html or "").lower()
        # X SPA 挂载点：正常页面都有这个 div
        has_react_root = "id=\"react-root\"" in raw_html or "id='react-root'" in raw_html
        # 黑屏状态下，<div id="react-root"> 存在但内部为空/极少内容
        return has_react_root
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
        # 推文详情页上评论区的局部错误（"出错了/Something went wrong"）不应判为全页错误。
        # 区分方法：推文详情页 URL 含 /status/ 且页面含有实质内容（推文正文/用户名等），
        # 说明主体内容已加载，只有评论区组件出错。
        if _is_tweet_detail_with_content(tab, url, text):
            return PageState.OK, "推文详情页主体正常，评论区局部错误已忽略"
        return PageState.TRANSIENT_ERROR, "命中临时错误页特征"

    if any(marker in text for marker in _LOGIN_MARKERS_STRONG):
        return PageState.LOGIN_REQUIRED, "命中登录提示特征"

    # JS 未执行空壳页检测：HTML 包含 noscript 降级文本但 SPA 未渲染
    if _is_js_not_executed(tab, text):
        return PageState.TRANSIENT_ERROR, "JS 未执行，页面为 noscript 空壳页"

    # Splash 黑屏检测：JS 已执行但 SPA 还在加载（黑屏+X logo 状态）
    if _is_splash_loading(tab, text):
        return PageState.SPLASH, "X 启动黑屏状态，SPA 尚未渲染内容"

    return PageState.OK, "页面状态正常"


def detect_cloudflare_challenge(tab) -> bool:
    """检测页面是否为 Cloudflare 五秒盾验证页。

    Cloudflare 验证页的特征比一般 challenge 更精准，
    需要用户在浏览器中手动完成验证。
    """
    text = _normalize_visible_text(tab)
    return any(marker in text for marker in _CLOUDFLARE_MARKERS)


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


def detect_end_of_timeline(tab) -> bool:
    """检测 X 搜索页面是否已到达时间线底部（无更多内容可加载）。

    当搜索结果很少（例如只有1-2条推文）时，页面不会有加载指示器，
    滚动也不会触发新的 SearchTimeline 请求。
    爬虫应识别此情况并停止等待，而非傻等数据包超时。

    检测策略：
    1. 检查页面是否存在"正在加载"指示器（若有则说明还在加载）
    2. 检查滚动位置是否已接近底部
    3. 综合判断是否已无更多内容
    """
    try:
        # 检测是否存在加载指示器
        loading_indicators = [
            '[data-testid="cellInnerDiv"] [role="progressbar"]',
            '[aria-label="Loading"]',
            '[aria-label="正在加载"]',
            'div[style*="spinner"]',
        ]
        for selector in loading_indicators:
            try:
                elem = tab.ele(selector, timeout=0.1)
                if elem:
                    return False  # 还在加载中
            except Exception:
                pass

        # 检测是否已滚动到底部（通过 JS 检查滚动位置）
        try:
            scroll_info = tab.run_js("""
                const scrollTop = window.scrollY || document.documentElement.scrollTop;
                const scrollHeight = document.documentElement.scrollHeight;
                const clientHeight = document.documentElement.clientHeight;
                const atBottom = scrollTop + clientHeight >= scrollHeight - 200;
                const timeline = document.querySelector('[data-testid="primaryColumn"]');
                const tweetCount = timeline ? timeline.querySelectorAll('[data-testid="tweet"]').length : 0;
                return { atBottom, scrollHeight, tweetCount };
            """)
            if isinstance(scroll_info, dict):
                at_bottom = scroll_info.get("atBottom", False)
                tweet_count = scroll_info.get("tweetCount", 0)
                # 如果已到底部且推文数很少，说明确实没有更多内容
                if at_bottom and tweet_count > 0 and tweet_count <= 10:
                    return True
        except Exception:
            pass

        return False
    except Exception:
        return False


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
# 包含中文"出错了。请尝试重新加载。"的局部组件错误（评论区加载失败等）
_RETRY_PAGE_MARKERS = [
    "something went wrong",
    "try again",
    "发生错误",
    "出错了",
    "请尝试重新加载",
]

import logging as _logging
_retry_logger = _logging.getLogger(__name__)


def detect_reply_area_error(tab) -> bool:
    """检测评论区是否出现局部加载错误（"出错了。请尝试重新加载。"弹出组件）。

    与 detect_page_state 不同，这里只检测评论区的局部错误组件，
    整页 detect_page_state 此时仍会返回 OK（因为主框架是正常的）。
    """
    try:
        text = _normalize_visible_text(tab)
        return any(marker in text for marker in ("出错了", "请尝试重新加载", "something went wrong", "try reloading"))
    except Exception:
        return False


def click_reply_retry_button(tab) -> bool:
    """点击评论区的"重试"按钮。

    适用于评论区局部加载错误时的恢复（截图中的"出错了。请尝试重新加载。"）。
    返回 True 表示找到并点击了按钮，False 表示未找到。
    """
    import time as _time
    try:
        # 优先精准选择器
        for selector in _RETRY_BUTTON_SELECTORS:
            try:
                btn = tab.ele(f"css:{selector}", timeout=0.8)
                if btn:
                    _retry_logger.info(f"评论区 Retry 按钮 selector={selector!r}，点击")
                    btn.click()
                    _time.sleep(0.5)
                    return True
            except Exception:
                continue
        # 兜底：遍历所有按钮找"重试"文字
        try:
            buttons = tab.eles("tag:button")
            for btn in buttons:
                try:
                    btn_text = (btn.text or "").strip().lower()
                    if btn_text in {"retry", "try again", "重试", "再试一次", "重新加载"}:
                        _retry_logger.info(f"评论区 Retry 按钮 text={btn_text!r}，点击")
                        btn.click()
                        _time.sleep(0.5)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
    except Exception as e:
        _retry_logger.debug(f"评论区 Retry 按钮点击异常（忽略）: {e}")
    return False


def click_retry_button_if_present(tab, *, max_attempts: int = 1) -> tuple[bool, bool]:
    import time as _time
    try:
        text = _normalize_visible_text(tab)
        if not any(marker in text for marker in _RETRY_PAGE_MARKERS):
            return False, False

        clicked = False
        for attempt in range(max(1, max_attempts)):
            _found = False
            # 尝试 CSS 选择器
            for selector in _RETRY_BUTTON_SELECTORS:
                try:
                    btn = tab.ele(f"css:{selector}", timeout=1.0)
                    if btn:
                        _retry_logger.info(
                            f"Retry 按钮 attempt={attempt+1}/{max_attempts} "
                            f"selector={selector!r}，点击..."
                        )
                        btn.click()
                        clicked = True
                        _found = True
                        break
                except Exception:
                    continue

            # 兜底：遍历所有按钮文字
            if not _found:
                try:
                    buttons = tab.eles("tag:button")
                    for btn in buttons:
                        try:
                            btn_text = (btn.text or "").strip().lower()
                            if btn_text in {"retry", "try again", "重试", "再试一次"}:
                                _retry_logger.info(
                                    f"Retry 按钮 attempt={attempt+1} text={btn_text!r}，点击..."
                                )
                                btn.click()
                                clicked = True
                                _found = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            if not clicked:
                return False, False

            # 点击后等待页面响应
            _time.sleep(0.8)

            # 检测页面是否已恢复
            new_state, _ = detect_page_state(tab)
            if new_state == PageState.OK:
                _retry_logger.info(
                    f"Retry 点击后页面已恢复正常（attempt={attempt+1})"
                )
                return True, True

            # 未恢复，等待后再试
            if attempt < max_attempts - 1:
                _time.sleep(0.8)
                text = _normalize_visible_text(tab)
                if not any(marker in text for marker in _RETRY_PAGE_MARKERS):
                    new_state, _ = detect_page_state(tab)
                    return True, new_state == PageState.OK

        return clicked, False

    except Exception as e:
        _retry_logger.debug(f"Retry 按钮检测异常（忽略）: {e}")
        return False, False

