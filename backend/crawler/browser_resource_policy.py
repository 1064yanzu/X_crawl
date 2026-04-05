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

# 图片拦截模式（tab 级别，兼容接管模式）
_IMAGE_BLOCK_PATTERNS = [
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.gif",
    "*.webp",
    "*.svg",
    "*.ico",
    "*.bmp",
    "*pbs.twimg.com/profile_images/*",
    "*pbs.twimg.com/media/*",
    "*pbs.twimg.com/card_img/*",
    "*twimg.com/*.jpg*",
    "*twimg.com/*.png*",
    "*twimg.com/*.gif*",
    "*twimg.com/*.webp*",
]


def apply_browser_option_policies(co) -> None:
    """对 ChromiumOptions 应用资源策略（仅对独立启动模式有效）。"""
    co.no_imgs(bool(getattr(settings, "browser_block_images", False)))


def apply_tab_resource_policies(tab) -> None:
    """
    对新建标签页应用运行时资源拦截策略。
    使用 DevTools Protocol blocked_urls，兼容接管模式与独立模式。
    """
    blocked_urls: list[str] = []
    if bool(getattr(settings, "browser_block_images", False)):
        blocked_urls.extend(_IMAGE_BLOCK_PATTERNS)
    if bool(getattr(settings, "browser_block_videos", False)):
        blocked_urls.extend(_VIDEO_BLOCK_PATTERNS)

    try:
        tab.set.blocked_urls(blocked_urls or None)
        if blocked_urls:
            logger.debug(
                "已对标签页应用资源拦截：图片=%s 视频=%s",
                bool(getattr(settings, "browser_block_images", False)),
                bool(getattr(settings, "browser_block_videos", False)),
            )
    except Exception as e:
        logger.warning("应用标签页资源拦截策略失败: %s", e)
