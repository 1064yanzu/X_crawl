"""
浏览器资源策略。

统一管理浏览器级和标签页级的资源加载限制，避免策略散落在
`browser.py` / `browser_pool.py` / 业务抓取逻辑里。
"""
from __future__ import annotations

import logging

from config import settings

logger = logging.getLogger(__name__)

_VIDEO_BLOCK_PATTERNS = [
    "*video.twimg.com/*",
    "*twimg.com/amplify_video*",
    "*.m3u8*",
    "*.mp4*",
    "*.webm*",
    "*.ts*",
    "*.m4s*",
    "*.mpd*",
]


def apply_browser_option_policies(co) -> None:
    """对 ChromiumOptions 应用资源策略。"""
    co.no_imgs(bool(getattr(settings, "browser_block_images", False)))


def apply_tab_resource_policies(tab) -> None:
    """对新建标签页应用运行时资源拦截策略。"""
    blocked_urls: list[str] = []
    if bool(getattr(settings, "browser_block_videos", False)):
        blocked_urls.extend(_VIDEO_BLOCK_PATTERNS)

    try:
        tab.set.blocked_urls(blocked_urls or None)
        if blocked_urls:
            logger.debug("已对标签页应用资源拦截策略: %s", blocked_urls)
    except Exception as e:
        logger.warning("应用标签页资源拦截策略失败: %s", e)
