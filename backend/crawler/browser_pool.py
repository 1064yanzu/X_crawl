"""
浏览器实例池（Browser Pool）

设计思想：
- 并发数 = N → N 个浏览器实例（槽位 slot），每个实例独立端口 + Profile 目录
- 同一个 slot 内不同平台（X / 微博）的任务共享同一个浏览器实例
  （Cookie 域名不同天然隔离，无需分开）
- 同一个 slot 内同一平台的任务不会同时存在（调度器保证）

使用流程：
    inst = pool.acquire(task_id, platform)  # 借出 slot 对应的实例
    tab = inst.new_tab()                    # 在该实例上创建 tab
    ...
    pool.release(task_id)                   # 归还 slot
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from DrissionPage import Chromium

logger = logging.getLogger(__name__)

_POOL_PROFILE_BASE = str(Path.home() / ".xcrawl-browser-instances")


class BrowserInstance:
    """单个浏览器实例的封装，持有独立端口和 profile 目录。"""

    def __init__(self, instance_id: int):
        self.instance_id = instance_id
        self.profile_dir = os.path.join(_POOL_PROFILE_BASE, f"instance-{instance_id}")
        self._browser: Optional["Chromium"] = None
        self._lock = threading.Lock()

    @property
    def is_alive(self) -> bool:
        if self._browser is None:
            return False
        try:
            _ = self._browser.latest_tab
            return True
        except Exception:
            return False

    def get_browser(self) -> "Chromium":
        """获取或创建浏览器实例（懒初始化）。"""
        with self._lock:
            if self._browser is not None and self.is_alive:
                return self._browser
            self._browser = self._create_browser()
            return self._browser

    def _create_browser(self) -> "Chromium":
        from DrissionPage import Chromium, ChromiumOptions
        from crawler.browser import (
            _pick_free_local_port,
            _resolve_browser_paths,
            _cleanup_stale_singleton_locks,
            _is_user_data_locked,
        )
        from crawler.stealth import apply_stealth_to_tab
        from crawler.platform_runtime import (
            should_force_headless_on_linux,
            linux_headless_args_enabled,
        )
        from config import settings

        os.makedirs(self.profile_dir, exist_ok=True)

        # 清理孤儿锁文件
        if _is_user_data_locked(self.profile_dir):
            _cleanup_stale_singleton_locks(self.profile_dir)

        co = ChromiumOptions()
        port = _pick_free_local_port()
        co.set_local_port(port)
        co.set_user_data_path(self.profile_dir)

        exec_path, _ = _resolve_browser_paths()
        if exec_path:
            co.set_browser_path(exec_path)

        if settings.browser_proxy:
            co.set_proxy(settings.browser_proxy)

        effective_headless = bool(settings.browser_headless)
        if should_force_headless_on_linux(browser_headless=effective_headless):
            effective_headless = True

        if effective_headless:
            co.headless(True)
            _REAL_UA = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
            )
            co.set_argument("--user-agent", _REAL_UA)

        if linux_headless_args_enabled(
            browser_linux_hardening=bool(settings.browser_linux_hardening),
            browser_headless=effective_headless,
        ):
            co.set_argument("--no-sandbox")
            co.set_argument("--disable-dev-shm-usage")
            co.set_argument("--disable-gpu")
            co.set_argument("--disable-setuid-sandbox")

        co.set_argument("--window-size", "1366,860")
        co.set_argument("--lang", "zh-CN,zh,en,en-GB,en-US")
        co.set_argument("--accept-lang", "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6")
        co.set_argument("--disable-blink-features", "AutomationControlled")
        co.set_argument("--disable-infobars")
        co.set_argument("--no-first-run")
        co.set_argument("--no-default-browser-check")

        load_mode = settings.browser_load_mode if settings.browser_load_mode in ("normal", "eager", "none") else "normal"
        co.set_load_mode(load_mode)
        co.no_imgs(settings.browser_block_images)
        co.mute(True)

        logger.info(f"[BrowserPool] 启动浏览器实例 #{self.instance_id}，port={port}，profile={self.profile_dir}")
        browser = Chromium(co)
        logger.info(f"[BrowserPool] 浏览器实例 #{self.instance_id} 就绪")
        return browser

    def new_tab(self):
        """在此实例上创建新 tab（已注入 stealth）。"""
        from crawler.stealth import apply_stealth_to_tab
        from config import settings
        import sys

        background = bool(settings.browser_background_tabs)
        browser = self.get_browser()
        tab = browser.new_tab(background=background)
        apply_stealth_to_tab(tab, enabled=True)
        return tab

    def close(self) -> None:
        """关闭浏览器实例。"""
        with self._lock:
            if self._browser is not None:
                try:
                    self._browser.quit()
                    logger.info(f"[BrowserPool] 浏览器实例 #{self.instance_id} 已关闭")
                except Exception as e:
                    logger.warning(f"[BrowserPool] 关闭实例 #{self.instance_id} 出错: {e}")
                finally:
                    self._browser = None


class _Slot:
    """
    一个并发槽位。

    每个 slot 持有一个 BrowserInstance，可同时被不同平台的任务使用。
    slot.platforms 记录当前正在使用此 slot 的 { platform: task_id }。
    """

    def __init__(self, slot_id: int, instance: BrowserInstance):
        self.slot_id = slot_id
        self.instance = instance
        # platform -> task_id（同一平台同时只有一个任务）
        self.platforms: dict[str, str] = {}

    @property
    def is_empty(self) -> bool:
        return len(self.platforms) == 0

    def has_platform(self, platform: str) -> bool:
        return platform in self.platforms

    def occupy(self, platform: str, task_id: str) -> None:
        self.platforms[platform] = task_id

    def vacate_task(self, task_id: str) -> None:
        to_remove = [p for p, tid in self.platforms.items() if tid == task_id]
        for p in to_remove:
            del self.platforms[p]


class BrowserPool:
    """
    浏览器实例池（按槽位 slot 分配）。

    - 共 max_size 个 slot，每个 slot 绑定一个 BrowserInstance
    - 同一个 slot 内不同平台（X / 微博）的任务共享同一个浏览器实例
    - 同一个 slot 内同一平台只能有一个任务
    - acquire(task_id, platform) 找到一个该平台空闲的 slot，借出其实例
    - release(task_id) 从 slot 中移除该任务，slot 可被复用
    """

    def __init__(self, max_size: int = 2):
        self._max_size = max_size
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        # slot_id -> _Slot
        self._slots: dict[int, _Slot] = {}
        # task_id -> slot_id（快速反查）
        self._task_slot: dict[str, int] = {}
        self._next_id = 0

    def _find_slot_for(self, platform: str) -> Optional[_Slot]:
        """
        找到一个可以容纳该平台任务的 slot。优先级：
        1. 已有实例且该平台空闲的 slot（共享实例）
        2. 完全空闲的 slot
        3. 新建 slot（未超上限时）
        调用方需持有锁。
        """
        # 1) 已有实例、该平台空闲、优先选已经有其他平台任务的（最大化共享）
        for slot in self._slots.values():
            if not slot.has_platform(platform) and not slot.is_empty:
                return slot

        # 2) 完全空闲的 slot
        for slot in self._slots.values():
            if slot.is_empty:
                return slot

        # 3) 新建
        if len(self._slots) < self._max_size:
            slot_id = self._next_id
            self._next_id += 1
            inst = BrowserInstance(slot_id)
            slot = _Slot(slot_id, inst)
            self._slots[slot_id] = slot
            return slot

        # 4) 所有 slot 该平台都被占用了
        return None

    def acquire(self, task_id: str, platform: str = "x", timeout: float = 120.0) -> tuple[BrowserInstance, int]:
        """
        借出一个浏览器实例给指定任务。

        Returns:
            (BrowserInstance, slot_id) 元组。slot_id 可用于账号池按索引分配不同账号。
        """
        deadline = time.monotonic() + timeout
        with self._condition:
            # 如果该 task 已持有 slot，直接返回
            if task_id in self._task_slot:
                slot = self._slots[self._task_slot[task_id]]
                return slot.instance, slot.slot_id

            while True:
                slot = self._find_slot_for(platform)
                if slot is not None:
                    slot.occupy(platform, task_id)
                    self._task_slot[task_id] = slot.slot_id
                    peers = ", ".join(f"{p}={tid[:8]}" for p, tid in slot.platforms.items() if tid != task_id)
                    peer_info = f"（共享: {peers}）" if peers else ""
                    logger.info(
                        f"[BrowserPool] task={task_id[:8]} platform={platform} → "
                        f"slot #{slot.slot_id}{peer_info}"
                    )
                    return slot.instance, slot.slot_id

                # 所有 slot 该平台都被占用，等待
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"[BrowserPool] 等待可用 slot 超时（{timeout}s），"
                        f"task={task_id[:8]}，platform={platform}"
                    )
                self._condition.wait(timeout=min(remaining, 2.0))

    def release(self, task_id: str) -> None:
        """释放任务占用的 slot 平台位。slot 本身和浏览器实例保留复用。"""
        with self._condition:
            slot_id = self._task_slot.pop(task_id, None)
            if slot_id is None:
                return
            slot = self._slots.get(slot_id)
            if slot is not None:
                slot.vacate_task(task_id)
                logger.info(
                    f"[BrowserPool] task={task_id[:8]} 释放 slot #{slot_id}，"
                    f"剩余占用: {dict(slot.platforms) or '空闲'}"
                )
            self._condition.notify_all()

    def close_all(self) -> None:
        """关闭所有浏览器实例（服务关闭时调用）。"""
        with self._lock:
            all_slots = list(self._slots.values())
            self._slots.clear()
            self._task_slot.clear()
        for slot in all_slots:
            slot.instance.close()

    def resize(self, new_max: int) -> None:
        """动态调整池大小（通常在配置变更时调用）。"""
        with self._condition:
            self._max_size = max(1, new_max)
            self._condition.notify_all()

    @property
    def max_size(self) -> int:
        return self._max_size

    def status(self) -> dict:
        with self._lock:
            slots_info = []
            for sid, slot in self._slots.items():
                slots_info.append({
                    "slot_id": sid,
                    "platforms": dict(slot.platforms),
                    "alive": slot.instance.is_alive,
                })
            return {
                "max_size": self._max_size,
                "total_slots": len(self._slots),
                "slots": slots_info,
            }


# ─── 全局单例 ───────────────────────────────────────────────────────────────

_pool: Optional[BrowserPool] = None
_pool_lock = threading.Lock()


def get_browser_pool() -> BrowserPool:
    """获取全局浏览器实例池（懒初始化，大小由配置决定）。"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from config import settings
                max_size = max(1, int(settings.crawler_max_concurrent_tasks))
                _pool = BrowserPool(max_size=max_size)
                logger.info(f"[BrowserPool] 初始化，max_size={max_size}")
    return _pool


def is_pool_mode_enabled() -> bool:
    """是否启用浏览器池模式（并发数 > 1 时自动启用）。"""
    from config import settings
    return int(settings.crawler_max_concurrent_tasks) > 1
