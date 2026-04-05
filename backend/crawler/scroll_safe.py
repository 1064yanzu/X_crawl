"""
带超时保护的 scroll 封装

解决 tab.scroll.to_bottom() 在某些页面状态下长时间卡死的问题。
使用 ThreadPoolExecutor 给 scroll 操作设置 8 秒硬超时，超时后回退 JS 方式，
确保主流程不被阻塞。
"""
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional

from crawler.utils import interruptible_sleep

logger = logging.getLogger(__name__)

_SCROLL_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="scroll-safe")
_SCROLL_TIMEOUT_SEC = 4.0


def safe_scroll_down(tab, px: int, *, task_id: Optional[str] = None) -> bool:
    try:
        future = _SCROLL_EXECUTOR.submit(tab.scroll.down, px)
        future.result(timeout=_SCROLL_TIMEOUT_SEC)
        return True
    except FuturesTimeoutError:
        logger.warning(f"scroll.down({px}) 超时（>{_SCROLL_TIMEOUT_SEC}s），回退到 JS 滚动")
        try:
            tab.run_js(f"window.scrollBy(0, {px})")
        except Exception as e:
            logger.debug(f"JS 回退滚动失败: {e}")
        return False
    except Exception as e:
        logger.debug(f"scroll.down({px}) 异常: {e}")
        try:
            tab.run_js(f"window.scrollBy(0, {px})")
        except Exception:
            pass
        return False


def safe_scroll_up(tab, px: int, *, task_id: Optional[str] = None) -> bool:
    try:
        future = _SCROLL_EXECUTOR.submit(tab.scroll.up, px)
        future.result(timeout=_SCROLL_TIMEOUT_SEC)
        return True
    except FuturesTimeoutError:
        logger.warning(f"scroll.up({px}) 超时（>{_SCROLL_TIMEOUT_SEC}s），回退到 JS 滚动")
        try:
            tab.run_js(f"window.scrollBy(0, -{px})")
        except Exception as e:
            logger.debug(f"JS 回退滚动失败: {e}")
        return False
    except Exception as e:
        logger.debug(f"scroll.up({px}) 异常: {e}")
        try:
            tab.run_js(f"window.scrollBy(0, -{px})")
        except Exception:
            pass
        return False


def safe_scroll_to_bottom(tab, *, task_id: Optional[str] = None) -> None:
    """单步策略：带超时保护调用 to_bottom()，超时回退 JS"""
    try:
        future = _SCROLL_EXECUTOR.submit(tab.scroll.to_bottom)
        future.result(timeout=_SCROLL_TIMEOUT_SEC)
    except FuturesTimeoutError:
        logger.warning(f"scroll.to_bottom() 超时（>{_SCROLL_TIMEOUT_SEC}s），回退到 JS 滚动到底部")
        try:
            tab.run_js("window.scrollTo(0, document.body.scrollHeight)")
        except Exception as e:
            logger.debug(f"JS 回退到底部失败: {e}")
    except Exception as e:
        logger.debug(f"scroll.to_bottom() 异常: {e}")
        try:
            tab.run_js("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
