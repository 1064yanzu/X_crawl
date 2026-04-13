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
    """对 ChromiumOptions 应用资源策略（仅对独立启动模式有效）。"""
    co.no_imgs(bool(getattr(settings, "browser_block_images", False)))


def apply_tab_resource_policies(tab) -> None:
    """
    对新建标签页应用运行时资源拦截策略。
    使用 DevTools Protocol blocked_urls，仅拦截视频/流媒体 URL。

    说明：
    - 图片禁用优先使用浏览器级 `no_imgs()`，由 Chromium 自身跳过图片加载。
    - 不再对图片使用 `blocked_urls` 进行 URL 级硬拦截。
      微博页面在无图模式下对某些 PNG 资源会反复重试；若同时做 URL 级 block，
      会出现 Network 面板请求数持续膨胀，最终拖死标签页。
    """
    blocked_urls: list[str] = []
    if bool(getattr(settings, "browser_block_videos", False)):
        blocked_urls.extend(_VIDEO_BLOCK_PATTERNS)

    try:
        tab.set.blocked_urls(blocked_urls or None)
        if blocked_urls:
            logger.debug(
                "已对标签页应用资源拦截：图片(browser级 no_imgs)=%s 视频(URL级)=%s",
                bool(getattr(settings, "browser_block_images", False)),
                bool(getattr(settings, "browser_block_videos", False)),
            )
    except Exception as e:
        logger.warning("应用标签页资源拦截策略失败: %s", e)
