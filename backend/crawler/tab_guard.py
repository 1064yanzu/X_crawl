"""
Tab 生命周期守卫

保证每个 tab 的 listener 和 tab 本身在任何退出路径（正常/异常）下都被正确清理。
消除 tab 和 listener 泄漏 — 浏览器不稳定的核心根因之一。

用法：
    with TabGuard(tab) as guard:
        guard.start_listener("SearchTimeline")
        tab.get(url)
        ...
    # 退出 with 块时自动 stop listener + close tab

    # 或者只管 listener，不关 tab（tab 由外部管理）：
    with TabGuard(tab, close_on_exit=False) as guard:
        guard.start_listener("TweetDetail")
        ...
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class TabGuard:
    """
    Tab 资源守卫，确保 listener 和 tab 在退出时必定清理。

    线程安全：多个线程可以引用同一个 TabGuard，但 close 只执行一次。
    """

    def __init__(self, tab, *, close_on_exit: bool = True):
        self._tab = tab
        self._close_on_exit = close_on_exit
        self._listener_active = False
        self._closed = False
        self._lock = threading.Lock()

    @property
    def tab(self):
        return self._tab

    def start_listener(self, pattern: str) -> None:
        """安全启动 listener，先停止已有的再启动新的。"""
        self._safe_stop_listener()
        try:
            self._tab.listen.start(pattern)
            self._listener_active = True
        except Exception as e:
            logger.warning("[TabGuard] 启动 listener 失败: %s", e)
            self._listener_active = False

    def restart_listener(self, pattern: str) -> None:
        """重新启动 listener（停→启）。"""
        self.start_listener(pattern)

    def _safe_stop_listener(self) -> None:
        """安全停止 listener，不抛异常。"""
        if not self._listener_active:
            return
        try:
            listener = getattr(self._tab, "listen", None)
            if listener is None:
                return
            if getattr(listener, "_driver", None) is None:
                return
            listener.stop()
        except Exception as e:
            logger.debug("[TabGuard] 停止 listener 失败（已忽略）: %s", e)
        finally:
            self._listener_active = False

    def close(self) -> None:
        """关闭 tab 及其 listener（幂等，多次调用安全）。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True

        self._safe_stop_listener()
        if self._close_on_exit:
            try:
                self._tab.close()
            except Exception as e:
                logger.debug("[TabGuard] 关闭 tab 失败（已忽略）: %s", e)

    def __enter__(self) -> "TabGuard":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def safe_stop_listener(tab) -> None:
    """无 guard 场景下安全停止 listener（兼容旧代码）。"""
    try:
        listener = getattr(tab, "listen", None)
        if listener is None:
            return
        if getattr(listener, "_driver", None) is None:
            return
        listener.stop()
    except Exception as e:
        logger.debug("[tab_guard] 停止 listener 失败（已忽略）: %s", e)
