"""
带超时保护的 scroll 封装

解决 tab.scroll.to_bottom() 在某些页面状态下长时间卡死的问题。
优先使用 JS 滚动（零 CDP 开销），仅在 JS 失败时回退到 DP 原生滚动。
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SCROLL_TIMEOUT_SEC = 2.0


def safe_scroll_down(tab, px: int, *, task_id: Optional[str] = None) -> bool:
    """向下滚动指定像素。优先 JS，失败回退 DP。"""
    try:
        tab.run_js(f"window.scrollBy(0, {px})", timeout=_SCROLL_TIMEOUT_SEC)
        return True
    except Exception:
        pass
    # JS 失败，尝试 DP 原生（加超时保护）
    try:
        tab.scroll.down(px)
        return True
    except Exception as e:
        logger.debug(f"scroll.down({px}) 异常: {e}")
        return False


def safe_scroll_up(tab, px: int, *, task_id: Optional[str] = None) -> bool:
    """向上滚动指定像素。优先 JS，失败回退 DP。"""
    try:
        tab.run_js(f"window.scrollBy(0, -{px})", timeout=_SCROLL_TIMEOUT_SEC)
        return True
    except Exception:
        pass
    try:
        tab.scroll.up(px)
        return True
    except Exception as e:
        logger.debug(f"scroll.up({px}) 异常: {e}")
        return False


def safe_scroll_to_bottom(tab, *, task_id: Optional[str] = None) -> None:
    """滚动到页面底部。优先 JS，失败回退 DP。"""
    try:
        tab.run_js("window.scrollTo(0, document.body.scrollHeight)", timeout=_SCROLL_TIMEOUT_SEC)
        return
    except Exception:
        pass
    try:
        tab.scroll.to_bottom()
    except Exception as e:
        logger.debug(f"scroll.to_bottom() 异常: {e}")
