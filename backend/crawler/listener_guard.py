"""
统一的 DrissionPage listener 管理器

防止 tab.listen 泄漏：
- safe_start / safe_stop 提供防御性的 listener 操作
- TabListenerGuard 上下文管理器确保 listener 在退出时一定被清理
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def safe_stop_listener(tab, *, reason: str = "") -> bool:
    """
    安全停止 tab 的网络监听。

    防御性设计：检查 tab / listener / driver 是否为 None，
    忽略所有异常（监听可能已经停止或 tab 已断连）。

    Returns:
        True = 成功停止或已经停止，False = 操作失败
    """
    if tab is None:
        return True
    try:
        listener = getattr(tab, "listen", None)
        if listener is None:
            return True
        # DrissionPage 内部检查 _driver 是否存在
        driver = getattr(listener, "_driver", None)
        if driver is None:
            return True
        listener.stop()
        return True
    except Exception as e:
        if reason:
            logger.debug("[ListenerGuard] 停止 listener 失败（%s）: %s", reason, e)
        return False


def safe_start_listener(tab, targets, *, reason: str = "") -> bool:
    """
    安全启动 tab 的网络监听。

    先确保旧 listener 已停止，再启动新的。

    Args:
        tab: DrissionPage 标签页
        targets: 监听目标（URL 模式字符串或正则）
        reason: 日志标记

    Returns:
        True = 启动成功，False = 启动失败
    """
    safe_stop_listener(tab, reason=f"pre-start:{reason}")
    try:
        tab.listen.start(targets)
        return True
    except Exception as e:
        logger.warning("[ListenerGuard] 启动 listener 失败（%s）: %s", reason, e)
        return False


class TabListenerGuard:
    """
    上下文管理器：进入时启动 listener，退出时保证关闭。

    用法：
        with TabListenerGuard(tab, "SearchTimeline") as guard:
            # ... 使用 tab.listen.wait(...)  ...
            pass
        # 退出时 listener 一定被 stop

    即使 with 块内发生异常，listener 也会被安全关闭。
    """

    def __init__(self, tab, targets, *, reason: str = ""):
        self.tab = tab
        self.targets = targets
        self.reason = reason
        self.started = False

    def __enter__(self):
        self.started = safe_start_listener(
            self.tab, self.targets, reason=self.reason
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        safe_stop_listener(self.tab, reason=f"guard-exit:{self.reason}")
        self.started = False
        return False  # 不吞异常
