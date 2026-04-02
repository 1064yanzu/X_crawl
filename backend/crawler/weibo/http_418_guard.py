from __future__ import annotations

import logging
from typing import Callable, Optional

from crawler.utils import interruptible_sleep

logger = logging.getLogger(__name__)

_HTTP_418_MARKERS = (
    "http error 418",
    "该网页无法正常运作",
    "如果问题仍然存在，请与网站所有者联系",
)
_ERROR_PAGE_URL_MARKERS = (
    "chrome-error://",
    "edge-error://",
)


def detect_weibo_http_418(tab) -> bool:
    """检测微博页面是否落入浏览器 HTTP 418 错误页。"""
    chunks: list[str] = []

    for attr in ("url", "title"):
        try:
            value = getattr(tab, attr, "") or ""
        except Exception:
            value = ""
        if value:
            chunks.append(str(value).lower())

    try:
        html = tab.html or ""
    except Exception:
        html = ""
    if html:
        chunks.append(str(html).lower()[:20_000])

    text = "\n".join(chunks)
    if not text:
        return False

    if any(marker in text for marker in _HTTP_418_MARKERS):
        return True
    return any(marker in text for marker in _ERROR_PAGE_URL_MARKERS) and "418" in text


def wait_weibo_http_418_cooldown(
    *,
    task_id: Optional[str],
    cooldown_seconds: float,
    context: str,
    phase_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """命中微博 418 后执行长冷却，等待站点解封后再继续。"""
    wait_seconds = max(60.0, float(cooldown_seconds))
    wait_minutes = max(1, round(wait_seconds / 60))
    message = (
        f"微博{context}触发 HTTP 418，已进入冷却，"
        f"等待约 {wait_minutes} 分钟后自动继续重试..."
    )
    logger.warning(message)
    if phase_callback is not None:
        try:
            phase_callback(message)
        except Exception:
            logger.debug("更新微博 418 冷却阶段文案失败", exc_info=True)
    interruptible_sleep(wait_seconds, task_id=task_id)
