"""
浏览器生命周期管理

核心目标：让浏览器"永远不出问题"。

功能：
1. 页面计数器 — 追踪每个 BrowserInstance 的导航次数，达到阈值触发软重启
2. 健康心跳守护线程 — 周期性探测所有活跃浏览器实例，主动发现死亡/卡死/内存超标
3. Tab 存活探针 — 操作前轻量检测 tab 是否可用，避免在死 tab 上等超时
4. Debug 文件自动清理 — 定期清理过期的调试截图和 HTML
5. 统一资源清理入口 — 任务结束时一次性清理所有模块级字典
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from crawler.browser_pool import BrowserInstance

logger = logging.getLogger(__name__)

# =====================================================================
#  1. 页面计数器 — 追踪导航次数，支撑 browser_restart_every_n_pages
# =====================================================================

_page_counts: dict[int, int] = {}  # instance_id -> 累计导航次数
_page_counts_lock = threading.Lock()


def record_navigation(instance_id: int) -> int:
    """记录一次页面导航，返回当前累计次数。"""
    with _page_counts_lock:
        _page_counts[instance_id] = _page_counts.get(instance_id, 0) + 1
        return _page_counts[instance_id]


def get_navigation_count(instance_id: int) -> int:
    with _page_counts_lock:
        return _page_counts.get(instance_id, 0)


def reset_navigation_count(instance_id: int) -> None:
    with _page_counts_lock:
        _page_counts.pop(instance_id, None)


def should_recycle(instance_id: int) -> bool:
    """判断实例是否需要回收（达到 browser_restart_every_n_pages）。"""
    from config import settings
    threshold = settings.browser_restart_every_n_pages
    if threshold <= 0:
        return False
    return get_navigation_count(instance_id) >= threshold


def recycle_instance(instance: "BrowserInstance") -> bool:
    """
    软重启浏览器实例：关闭旧 Chrome 进程 → 重置计数 → 下次 get_browser() 自动拉起新的。

    Returns:
        True = 成功回收，False = 回收失败或不需要
    """
    iid = instance.instance_id
    if not should_recycle(iid):
        return False

    count = get_navigation_count(iid)
    logger.info(
        "[Lifecycle] 实例 #%s 已导航 %d 页，达到回收阈值，执行软重启...",
        iid, count,
    )

    try:
        instance.close()
        reset_navigation_count(iid)
        logger.info("[Lifecycle] 实例 #%s 软重启完成，计数已重置", iid)
        return True
    except Exception as e:
        logger.warning("[Lifecycle] 实例 #%s 软重启失败: %s", iid, e)
        return False


# =====================================================================
#  2. Tab 存活探针 — 操作前轻量检测 tab 是否可用
# =====================================================================

def is_tab_alive(tab) -> bool:
    """
    轻量检测 tab 是否还能响应 CDP 命令。

    使用 run_js("1") 执行最简单的 JS 表达式，超时 2 秒。
    比 tab.url 更可靠（url 可能是缓存值）。
    """
    if tab is None:
        return False
    try:
        result = tab.run_js("1", timeout=2)
        return result is not None
    except Exception:
        return False


def ensure_tab_or_recreate(tab, browser_instance: "BrowserInstance"):
    """
    检测 tab 是否存活。若已死，关闭旧 tab 并创建新的。

    Returns:
        (tab, recreated): 可用的 tab 以及是否是新创建的
    """
    if is_tab_alive(tab):
        return tab, False

    logger.warning(
        "[Lifecycle] Tab 不可达（instance=#%s），创建新 tab...",
        browser_instance.instance_id,
    )
    # 尝试关闭旧 tab
    try:
        tab.close()
    except Exception:
        pass

    new_tab = browser_instance.new_tab()
    return new_tab, True


# =====================================================================
#  3. 健康心跳守护线程 — 周期性探测所有活跃浏览器实例
# =====================================================================

_heartbeat_thread: Optional[threading.Thread] = None
_heartbeat_stop = threading.Event()
_HEARTBEAT_INTERVAL = 30.0  # 秒


def _heartbeat_loop():
    """后台线程：周期性检查所有 pool 中的浏览器实例健康状态。

    检查项（从快到慢）：
    1. 进程是否存活（psutil.pid_exists）
    2. 内存是否超标（进程树 RSS > 阈值则标记延迟回收，不直接 quit）
    """
    while not _heartbeat_stop.wait(timeout=_HEARTBEAT_INTERVAL):
        try:
            from crawler.browser_pool import get_browser_pool
            from crawler.browser_health import is_memory_pressure, get_browser_memory_mb
            from config import settings
            pool = get_browser_pool()
            mem_limit = float(getattr(settings, "browser_memory_limit_mb", 2500.0))

            with pool._lock:
                all_slots = list(pool._slots.values())
                all_aux = [
                    (tid, inst)
                    for tid, inst_list in pool._aux_instances.items()
                    for inst in inst_list
                ]

            # 检查主实例
            for slot in all_slots:
                inst = slot.instance
                if inst._browser is None:
                    continue  # 未被使用的 slot，跳过

                if not inst.is_alive:
                    platforms = dict(slot.platforms)
                    logger.warning(
                        "[Heartbeat] 实例 #%s 浏览器进程已死（slot=%s, platforms=%s），"
                        "标记为待重建...",
                        inst.instance_id, slot.slot_id, platforms,
                    )
                    with inst._lock:
                        inst._browser = None
                    continue

                # 内存检测：标记延迟回收（不直接 quit，避免断开活跃中的 CDP 连接）
                if is_memory_pressure(inst._browser, threshold_mb=mem_limit):
                    mem_mb = get_browser_memory_mb(inst._browser)
                    if not inst._recycle_requested:
                        inst._recycle_requested = True
                        logger.info(
                            "[Heartbeat] 实例 #%s 内存 %.0fMB 超标（阈值 %.0fMB），"
                            "已标记延迟回收（下次安全时机执行）",
                            inst.instance_id, mem_mb or 0, mem_limit,
                        )

            # 检查辅助实例
            for task_id, inst in all_aux:
                if inst._browser is None:
                    continue
                if not inst.is_alive:
                    logger.warning(
                        "[Heartbeat] 辅助实例 #%s (task=%s) 浏览器进程已死，标记为待重建...",
                        inst.instance_id, task_id[:8],
                    )
                    with inst._lock:
                        inst._browser = None
                    continue

                # 辅助实例也标记延迟回收
                if is_memory_pressure(inst._browser, threshold_mb=mem_limit):
                    mem_mb = get_browser_memory_mb(inst._browser)
                    if not inst._recycle_requested:
                        inst._recycle_requested = True
                        logger.info(
                            "[Heartbeat] 辅助实例 #%s (task=%s) 内存 %.0fMB 超标，"
                            "已标记延迟回收",
                            inst.instance_id, task_id[:8], mem_mb or 0,
                        )

        except Exception as e:
            logger.debug("[Heartbeat] 心跳检测异常（非致命）: %s", e)


def start_heartbeat():
    """启动后台健康心跳守护线程（幂等）。"""
    global _heartbeat_thread
    if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
        return

    _heartbeat_stop.clear()
    _heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        daemon=True,
        name="browser-heartbeat",
    )
    _heartbeat_thread.start()
    logger.info("[Lifecycle] 浏览器健康心跳线程已启动（间隔 %.0fs）", _HEARTBEAT_INTERVAL)


def stop_heartbeat():
    """停止后台心跳线程。"""
    _heartbeat_stop.set()
    if _heartbeat_thread is not None:
        _heartbeat_thread.join(timeout=5)


# =====================================================================
#  4. Debug 文件自动清理
# =====================================================================

_DEBUG_DIR = Path(__file__).resolve().parent.parent / "logs" / "debug"
_CLEANUP_INTERVAL = 600.0    # 10 分钟检查一次
_MAX_DEBUG_AGE = 3600.0      # 文件超过 1 小时自动删除
_MAX_DEBUG_FILES = 100        # 目录最多保留 100 个文件
_cleanup_thread: Optional[threading.Thread] = None
_cleanup_stop = threading.Event()


def _debug_cleanup_loop():
    """后台线程：定期清理过期 debug 文件。"""
    while not _cleanup_stop.wait(timeout=_CLEANUP_INTERVAL):
        try:
            _cleanup_debug_files()
        except Exception as e:
            logger.debug("[Lifecycle] 清理 debug 文件异常: %s", e)


def _cleanup_debug_files():
    """清理 debug 目录中的过期文件。"""
    if not _DEBUG_DIR.exists():
        return

    now = time.time()
    files = []
    try:
        for f in _DEBUG_DIR.iterdir():
            if f.is_file():
                files.append((f, f.stat().st_mtime))
    except Exception:
        return

    # 删除过期文件
    removed = 0
    for f, mtime in files:
        if now - mtime > _MAX_DEBUG_AGE:
            try:
                f.unlink(missing_ok=True)
                removed += 1
            except Exception:
                pass

    # 数量超限时删除最旧的
    remaining = [(f, mt) for f, mt in files if f.exists()]
    if len(remaining) > _MAX_DEBUG_FILES:
        remaining.sort(key=lambda x: x[1])
        for f, _ in remaining[:len(remaining) - _MAX_DEBUG_FILES]:
            try:
                f.unlink(missing_ok=True)
                removed += 1
            except Exception:
                pass

    if removed > 0:
        logger.info("[Lifecycle] 已清理 %d 个过期 debug 文件", removed)


def start_debug_cleanup():
    """启动 debug 文件清理线程（幂等）。"""
    global _cleanup_thread
    if _cleanup_thread is not None and _cleanup_thread.is_alive():
        return

    _cleanup_stop.clear()
    _cleanup_thread = threading.Thread(
        target=_debug_cleanup_loop,
        daemon=True,
        name="debug-cleanup",
    )
    _cleanup_thread.start()
    logger.info("[Lifecycle] Debug 文件清理线程已启动")


def stop_debug_cleanup():
    _cleanup_stop.set()
    if _cleanup_thread is not None:
        _cleanup_thread.join(timeout=5)


# =====================================================================
#  5. 统一资源清理入口 — 任务结束时清理所有模块级字典
# =====================================================================

def cleanup_task_resources(task_id: str) -> None:
    """
    任务结束时的统一清理入口。

    一次性清理散落在各模块中的 per-task 状态字典，防止内存泄漏。
    在 crawl_service.py 任务结束时调用。
    """
    # 1. page_health: _per_task_errors, _snapshot_last_save
    try:
        from crawler.page_health import _error_lock, _per_task_errors, _snapshot_lock, _snapshot_last_save
        with _error_lock:
            _per_task_errors.pop(task_id, None)
        with _snapshot_lock:
            _snapshot_last_save.pop(task_id, None)
    except Exception:
        pass

    # 2. circuit_breaker
    try:
        from crawler.circuit_breaker import get_breaker
        get_breaker().cleanup(task_id)
    except Exception:
        pass

    # 3. rate_tracker
    try:
        from crawler.rate_tracker import get_tracker
        get_tracker().cleanup_task(task_id)
    except Exception:
        pass

    # 4. runtime_metrics
    try:
        from crawler.runtime_metrics import clear_metrics
        clear_metrics(task_id)
    except Exception:
        pass

    logger.debug("[Lifecycle] 已清理 task=%s 的所有模块级资源", task_id[:8])


# =====================================================================
#  6. 服务生命周期：启动/停止所有后台守护线程
# =====================================================================

def start_all():
    """服务启动时调用：启动所有后台守护线程。"""
    start_heartbeat()
    start_debug_cleanup()
    # 首次启动时立即清理一次 debug 文件
    try:
        _cleanup_debug_files()
    except Exception:
        pass


def stop_all():
    """服务关闭时调用：停止所有后台守护线程。"""
    stop_heartbeat()
    stop_debug_cleanup()
