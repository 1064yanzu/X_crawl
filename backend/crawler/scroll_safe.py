"""
带超时保护的 scroll 封装

解决 tab.scroll.to_bottom() 在某些页面状态下长时间卡死的问题。
优先使用 DrissionPage 原生滚动 API，仅在原生 API 失败时回退到 JS 滚动。
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SCROLL_TIMEOUT_SEC = 2.0


def safe_scroll_down(tab, px: int, *, task_id: Optional[str] = None) -> bool:
    """向下滚动指定像素。优先 DP 原生，失败回退 JS。"""
    try:
        tab.scroll.down(px)
        return True
    except Exception:
        pass
    # DP 原生失败，尝试 JS 回退
    try:
        tab.run_js(f"window.scrollBy(0, {px})", timeout=_SCROLL_TIMEOUT_SEC)
        return True
    except Exception as e:
        logger.debug(f"scroll.down({px}) JS 回退也失败: {e}")
        return False


def safe_scroll_up(tab, px: int, *, task_id: Optional[str] = None) -> bool:
    """向上滚动指定像素。优先 DP 原生，失败回退 JS。"""
    try:
        tab.scroll.up(px)
        return True
    except Exception:
        pass
    try:
        tab.run_js(f"window.scrollBy(0, -{px})", timeout=_SCROLL_TIMEOUT_SEC)
        return True
    except Exception as e:
        logger.debug(f"scroll.up({px}) JS 回退也失败: {e}")
        return False


def safe_scroll_to_bottom(tab, *, task_id: Optional[str] = None) -> None:
    """滚动到页面底部。优先 DP 原生，失败回退 JS。"""
    try:
        tab.scroll.to_bottom()
        return
    except Exception:
        pass
    try:
        tab.run_js("window.scrollTo(0, document.body.scrollHeight)", timeout=_SCROLL_TIMEOUT_SEC)
    except Exception as e:
        logger.debug(f"scroll.to_bottom() JS 回退也失败: {e}")
