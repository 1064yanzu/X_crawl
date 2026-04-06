"""
浏览器实例池（Browser Pool）

设计思想：
- 并发数 = N → N 个浏览器实例（槽位 slot），每个实例独立端口 + Profile 目录
- 默认优先给任务独占浏览器实例；仅在池已打满时，才允许不同平台兜底共享同一个 slot
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
import shutil
import threading
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from DrissionPage import Chromium

try:
    import psutil  # type: ignore
except Exception:
    psutil = None

logger = logging.getLogger(__name__)

# 全局关闭标志：lifespan shutdown 时设置，阻止 new_tab 在关闭期间触发浏览器重建
_shutting_down: bool = False


def set_shutting_down() -> None:
    """通知浏览器池：服务正在关闭，停止重建浏览器实例。"""
    global _shutting_down
    _shutting_down = True


_POOL_PROFILE_ROOT = str(Path.home() / ".xcrawl-browser-instances")


def _pool_profile_base(*, pid: Optional[int] = None) -> str:
    """
    返回当前进程专属的浏览器池 profile 根目录。

    多 worker / 多进程启动时，不同进程若共用同一组 profile 目录，
    会在"清理残留实例"阶段互相误杀对方正在使用的浏览器。
    """
    actual_pid = pid if pid is not None else os.getpid()
    return os.path.join(_POOL_PROFILE_ROOT, f"worker-{actual_pid}")


def compute_pool_max_size(
    max_per_platform: Optional[int] = None,
    *,
    cross_platform: Optional[bool] = None,
) -> int:
    """
    计算浏览器池应有的实际槽位上限。

    浏览器池大小严格等于 `crawler_max_concurrent_tasks`，不因跨平台并发
    而翻倍。不同平台的任务通过 slot 共享机制复用同一个浏览器实例，
    避免进程数膨胀导致资源浪费。
    """
    if max_per_platform is None:
        from config import settings

        max_per_platform = settings.crawler_max_concurrent_tasks

    return max(1, int(max_per_platform))


def _extract_flag_value(cmdline: list[str], flag: str) -> Optional[str]:
    prefix = f"{flag}="
    for idx, arg in enumerate(cmdline):
        if arg.startswith(prefix):
            return arg[len(prefix):]
        if arg == flag and idx + 1 < len(cmdline):
            return cmdline[idx + 1]
    return None


def _iter_managed_pool_roots(*, base_dir: Optional[str] = None) -> list[dict[str, object]]:
    if psutil is None:
        return []

    base_dir = os.path.abspath(base_dir or _pool_profile_base())
    roots: list[dict[str, object]] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            cmdline = list(proc.info.get("cmdline") or [])
            if not cmdline:
                continue

            joined = " ".join(cmdline).lower()
            name = str(proc.info.get("name") or "").lower()
            if "chrome" not in joined and "chromium" not in joined and "chrome" not in name and "chromium" not in name:
                continue
            if any(arg.startswith("--type=") for arg in cmdline):
                continue

            user_data = _extract_flag_value(cmdline, "--user-data-dir")
            if not user_data:
                continue
            resolved = os.path.abspath(os.path.expanduser(user_data))
            if not resolved.startswith(base_dir + os.sep):
                continue

            roots.append(
                {
                    "pid": int(proc.pid),
                    "create_time": float(proc.info.get("create_time") or 0.0),
                    "user_data_dir": resolved,
                    "debug_port": _extract_flag_value(cmdline, "--remote-debugging-port"),
                }
            )
        except Exception:
            continue

    roots.sort(key=lambda item: float(item.get("create_time") or 0.0))
    return roots


def _terminate_process_tree(pid: int) -> int:
    if psutil is None:
        return 0
    try:
        proc = psutil.Process(pid)
    except Exception:
        return 0

    victims: list["psutil.Process"] = []
    try:
        victims.extend(proc.children(recursive=True))
    except Exception:
        pass
    victims.append(proc)

    seen: set[int] = set()
    ordered: list["psutil.Process"] = []
    for item in victims:
        try:
            if item.pid in seen:
                continue
            seen.add(item.pid)
            ordered.append(item)
        except Exception:
            continue

    for item in reversed(ordered):
        try:
            item.terminate()
        except Exception:
            pass
    _, alive = psutil.wait_procs(ordered, timeout=2)
    for item in alive:
        try:
            item.kill()
        except Exception:
            pass
    psutil.wait_procs(alive, timeout=2)
    return len(ordered)


def cleanup_stale_pool_browsers(
    *,
    max_size: Optional[int] = None,
    base_dir: Optional[str] = None,
) -> dict[str, int]:
    """
    清理受 BrowserPool 管理的残留 Chrome 根进程。

    - 服务重启时：kill 掉所有使用 `~/.xcrawl-browser-instances/instance-*` profile 的旧实例
    - 池大小缩小时：保底确保根实例数不超过 max_size
    """
    roots = _iter_managed_pool_roots(base_dir=base_dir)
    if not roots:
        return {"roots_seen": 0, "killed_roots": 0, "killed_processes": 0}

    victims = roots if max_size is None else roots[max(0, max_size):]
    killed_roots = 0
    killed_processes = 0
    for item in victims:
        killed = _terminate_process_tree(int(item["pid"]))
        if killed > 0:
            killed_roots += 1
            killed_processes += killed

    if killed_roots > 0:
        logger.warning(
            "[BrowserPool] 已清理残留浏览器根实例 %s 个，相关进程 %s 个",
            killed_roots,
            killed_processes,
        )

    return {
        "roots_seen": len(roots),
        "killed_roots": killed_roots,
        "killed_processes": killed_processes,
    }


class BrowserInstance:
    """单个浏览器实例的封装，持有独立端口和 profile 目录。"""

    def __init__(self, instance_id: int):
        self.instance_id = instance_id
        self.profile_dir = os.path.join(_pool_profile_base(), f"instance-{instance_id}")
        self._browser: Optional["Chromium"] = None
        self._lock = threading.Lock()
        # ── Cookie 继承机制：新 tab 自动注入这些 cookie ──
        self._cookies_to_inject: list[dict] = []
        self._bound_account_id: Optional[str] = None
        self._bound_account_alias: Optional[str] = None

    @property
    def is_alive(self) -> bool:
        """检测浏览器进程是否存活。

        通过 psutil 检查进程是否存在（快速且不依赖 CDP），
        避免在 CDP 繁忙时误判为断连。仅当进程确实不存在时才返回 False。
        """
        if self._browser is None:
            return False
        try:
            # 优先通过进程 ID 检查（不走 CDP，不受 tab 繁忙影响）
            pid = getattr(self._browser, "process_id", None)
            if pid and psutil:
                try:
                    return psutil.pid_exists(pid)
                except Exception:
                    pass
            # fallback: CDP 探测
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
        from crawler.browser_resource_policy import apply_browser_option_policies
        from crawler.platform_runtime import (
            should_force_headless_on_linux,
            linux_headless_args_enabled,
        )
        from config import settings

        self._reset_profile_dir()

        # 清理孤儿锁文件
        if _is_user_data_locked(self.profile_dir):
            _cleanup_stale_singleton_locks(self.profile_dir)

        co = ChromiumOptions()
        port = _pick_free_local_port()
        co.set_local_port(port)
        co.set_user_data_path(self.profile_dir)
        co.set_argument("--profile-directory", "Default")

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
        if effective_headless:
            co.set_argument("--disable-blink-features", "AutomationControlled")
        co.set_argument("--disable-infobars")
        co.set_argument("--no-first-run")
        co.set_argument("--no-default-browser-check")
        # 禁止会话恢复：防止 profile 被脏数据污染时 Chrome 恢复历史标签页
        co.set_argument("--no-restore-last-session")
        co.set_argument("--disable-session-crashed-bubble")
        co.set_argument("--disable-features", "Translate,OptimizationHints,MediaRouter,DialMediaRouteProvider")

        load_mode = settings.browser_load_mode if settings.browser_load_mode in ("normal", "eager", "none") else "normal"
        co.set_load_mode(load_mode)
        apply_browser_option_policies(co)
        co.mute(True)
        if settings.browser_block_videos:
            logger.info(
                "[BrowserPool] 实例 #%s 已启用禁视频模式（browser_block_videos=True）",
                self.instance_id,
            )

        logger.info(f"[BrowserPool] 启动浏览器实例 #{self.instance_id}，port={port}，profile={self.profile_dir}")
        browser = Chromium(co)
        # 缩短 DrissionPage 内部超时（默认 30s），减少资源争抢时的无效等待
        try:
            browser.set.timeouts(base=10, page_load=15, script=10)
        except Exception as _te:
            logger.debug("[BrowserPool] 设置浏览器超时失败（非关键）: %s", _te)
        logger.info(f"[BrowserPool] 浏览器实例 #{self.instance_id} 就绪")
        return browser

    def _reset_profile_dir(self) -> None:
        """
        重建池实例的专用 profile 目录。

        浏览器池实例不依赖长期持久化登录态，任务启动时会自行注入 Cookie。
        因此前一次异常退出留下的脏 profile / 锁文件 / 偏好损坏，都应在新实例启动前清空，
        避免 Chrome 弹出『打开您的个人资料时出了点问题』或恢复历史标签页。
        """
        profile_path = Path(self.profile_dir)
        if profile_path.exists():
            try:
                shutil.rmtree(profile_path, ignore_errors=True)
                if profile_path.exists():
                    # ignore_errors 后目录仍存在（被文件锁占用），尝试只删非锁定文件
                    for child in profile_path.iterdir():
                        try:
                            if child.is_dir():
                                shutil.rmtree(child, ignore_errors=True)
                            else:
                                child.unlink(missing_ok=True)
                        except Exception:
                            pass
                    # 重点清除会话文件，防止 Chrome 恢复历史标签页
                    self._clear_session_files(profile_path)
                    logger.debug(
                        "[BrowserPool] 实例 #%s profile 部分清理完成（被锁定文件已跳过）",
                        self.instance_id,
                    )
                else:
                    logger.info(
                        "[BrowserPool] 已重置实例 #%s 的 profile 目录: %s",
                        self.instance_id,
                        self.profile_dir,
                    )
            except Exception as e:
                logger.debug(
                    "[BrowserPool] 重置实例 #%s 的 profile 目录异常，继续复用: %s",
                    self.instance_id,
                    e,
                )
        os.makedirs(self.profile_dir, exist_ok=True)
        # profile 存在但未完全清干净时，主动清除会话文件防止 Chrome 恢复历史 tab
        self._clear_session_files(Path(self.profile_dir))

    def _clear_session_files(self, profile_path: Path) -> None:
        """删除 Chrome 用于恢复上次会话的文件，防止新实例启动时自动恢复历史标签页。"""
        # Chrome 的会话文件存在 Default/ 子目录下
        default_dir = profile_path / "Default"
        session_files = [
            "Last Session",
            "Last Tabs",
            "Current Session",
            "Current Tabs",
            "Session Storage",
        ]
        for name in session_files:
            target = default_dir / name
            try:
                if target.is_file():
                    target.unlink(missing_ok=True)
                elif target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
            except Exception:
                pass

    def set_cookies(
        self,
        cookies: list[dict],
        *,
        account_id: Optional[str] = None,
        account_alias: Optional[str] = None,
    ) -> None:
        """设置此实例的 cookie 列表，后续新 tab 会自动注入这些 cookie。"""
        with self._lock:
            self._cookies_to_inject = list(cookies)
            self._bound_account_id = account_id
            self._bound_account_alias = account_alias

    def get_cookies(self) -> list[dict]:
        """返回此实例当前待注入的新 tab Cookie 副本。"""
        with self._lock:
            return list(self._cookies_to_inject)

    def get_bound_account(self) -> tuple[Optional[str], Optional[str]]:
        with self._lock:
            return self._bound_account_id, self._bound_account_alias

    def _inject_cookies_to_tab(self, tab) -> int:
        """将 _cookies_to_inject 注入指定 tab，返回注入数量。"""
        cookies = []
        with self._lock:
            cookies = list(self._cookies_to_inject)
        if not cookies:
            return 0
        injected = 0
        for c in cookies:
            name = c.get("name")
            if not name:
                continue
            try:
                cookie_dict = {
                    "name": name,
                    "value": c.get("value", ""),
                    "domain": c.get("domain", ".x.com"),
                    "path": c.get("path", "/"),
                }
                # DrissionPage 的 cookie 设置
                tab.set.cookies(cookie_dict)
                injected += 1
            except Exception:
                pass
        return injected

    def new_tab(self, *, _retried: bool = False):
        """在此实例上创建新 tab（已注入 stealth 和 cookie）。断连时自动重建浏览器实例。"""
        from crawler.browser_resource_policy import apply_tab_resource_policies
        from crawler.stealth import apply_stealth_to_tab
        from config import settings

        background = bool(settings.browser_background_tabs)
        try:
            browser = self.get_browser()
            tab = browser.new_tab(background=background)
            apply_stealth_to_tab(tab, enabled=True)
            apply_tab_resource_policies(tab)
            # ── 自动注入预设 cookie ──
            injected = self._inject_cookies_to_tab(tab)
            if injected > 0:
                logger.debug(f"[BrowserPool] 实例 #{self.instance_id} 新 tab 已注入 {injected} 条 cookie")
            return tab
        except Exception as e:
            err_name = type(e).__name__
            if "Disconnected" in err_name or "disconnected" in str(e).lower():
                if _retried or _shutting_down:
                    raise
                logger.warning(
                    f"[BrowserPool] 实例 #{self.instance_id} 页面断连，正在重建浏览器..."
                )
                with self._lock:
                    # 尝试关闭旧实例
                    if self._browser is not None:
                        try:
                            self._browser.quit()
                        except Exception:
                            pass
                        self._browser = None
                return self.new_tab(_retried=True)
            raise

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
                    self._bound_account_id = None
                    self._bound_account_alias = None


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
        self.idle_since: float | None = None

    @property
    def is_empty(self) -> bool:
        return len(self.platforms) == 0

    def has_platform(self, platform: str) -> bool:
        return platform in self.platforms

    def occupy(self, platform: str, task_id: str) -> None:
        self.platforms[platform] = task_id
        self.idle_since = None

    def vacate_task(self, task_id: str) -> None:
        to_remove = [p for p, tid in self.platforms.items() if tid == task_id]
        for p in to_remove:
            del self.platforms[p]
        if self.is_empty:
            self.idle_since = time.monotonic()


class BrowserPool:
    """
    浏览器实例池（按槽位 slot 分配）。

    - 共 max_size 个 slot，每个 slot 绑定一个 BrowserInstance
    - 默认优先为任务分配独占 slot；池打满后才允许不同平台共享同一个实例
    - 同一个 slot 内同一平台只能有一个任务
    - acquire(task_id, platform) 找到一个该平台空闲的 slot，借出其实例
    - acquire_aux(task_id, purpose) 为同一任务借出一个辅助浏览器实例（如 reply/comment worker）
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
        # ── 辅助浏览器实例（Pipeline reply/comment worker 专用）──
        # task_id -> list[BrowserInstance]  同一任务可借出多个辅助实例
        self._aux_instances: dict[str, list[BrowserInstance]] = {}
        self._aux_next_id = 10000  # 辅助实例 ID 从 10000 开始，避免与 slot ID 冲突

    def _find_slot_for(self, platform: str) -> Optional[_Slot]:
        """
        找到一个可以容纳该平台任务的 slot。优先级：
        1. 完全空闲的 slot（独占实例）
        2. 新建 slot（未超上限时）
        3. 已有其他平台任务、但该平台空闲的 slot（兜底共享）
        调用方需持有锁。
        """
        # 1) 完全空闲的 slot，优先独占，避免多线程同时驱动同一个 Chromium 实例
        for slot in self._slots.values():
            if slot.is_empty:
                return slot

        # 2) 新建 slot
        if len(self._slots) < self._max_size:
            slot_id = self._next_id
            self._next_id += 1
            inst = BrowserInstance(slot_id)
            slot = _Slot(slot_id, inst)
            self._slots[slot_id] = slot
            return slot

        # 3) 兜底共享其他平台已占用的实例
        for slot in self._slots.values():
            if not slot.has_platform(platform):
                return slot

        # 4) 所有 slot 该平台都被占用
        return None

    def _warm_instance(self, instance: BrowserInstance, *, reason: str) -> None:
        """尽早拉起浏览器进程，避免任务实际运行后才懒启动。"""
        getter = getattr(instance, "get_browser", None)
        if not callable(getter):
            return
        try:
            getter()
        except Exception as e:
            logger.warning("[BrowserPool] 预热浏览器实例失败（%s）: %s", reason, e)

    def acquire(self, task_id: str, platform: str = "x", timeout: float = 120.0) -> tuple[BrowserInstance, int]:
        """
        借出一个浏览器实例给指定任务。

        Returns:
            (BrowserInstance, slot_id) 元组。slot_id 可用于账号池按索引分配不同账号。
        """
        deadline = time.monotonic() + timeout
        assigned_instance: BrowserInstance | None = None
        assigned_slot_id: int | None = None
        with self._condition:
            # 如果该 task 已持有 slot，直接返回
            if task_id in self._task_slot:
                slot = self._slots[self._task_slot[task_id]]
                assigned_instance = slot.instance
                assigned_slot_id = slot.slot_id
            else:
                while assigned_instance is None:
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
                        assigned_instance = slot.instance
                        assigned_slot_id = slot.slot_id
                        break

                    # 所有 slot 该平台都被占用，等待
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"[BrowserPool] 等待可用 slot 超时（{timeout}s），"
                            f"task={task_id[:8]}，platform={platform}"
                        )
                    self._condition.wait(timeout=min(remaining, 2.0))

        assert assigned_instance is not None and assigned_slot_id is not None
        self._warm_instance(
            assigned_instance,
            reason=f"task={task_id[:8]} slot={assigned_slot_id}",
        )
        return assigned_instance, assigned_slot_id

    def acquire_aux(self, task_id: str, purpose: str = "reply") -> BrowserInstance:
        """
        为指定任务借出一个辅助浏览器实例（独立 Chrome 进程）。

        用于 Pipeline 的 reply/comment worker，使其与搜索 tab 完全并行
        （不共享 WebSocket 连接，避免 CDP 命令串行化）。

        辅助实例不占用 slot，而是独立管理，在 release(task_id) 时一并关闭。

        Args:
            task_id: 任务 ID（用于追踪和释放）
            purpose: 用途描述（reply/comment，仅用于日志）

        Returns:
            BrowserInstance: 独立的浏览器实例
        """
        with self._lock:
            aux_id = self._aux_next_id
            self._aux_next_id += 1

        inst = BrowserInstance(aux_id)
        with self._lock:
            if task_id not in self._aux_instances:
                self._aux_instances[task_id] = []
            self._aux_instances[task_id].append(inst)

        logger.info(
            f"[BrowserPool] task={task_id[:8]} 借出辅助浏览器实例 #{aux_id}（{purpose}）"
        )
        return inst

    def release(self, task_id: str) -> None:
        """释放任务占用的 slot 和所有辅助实例。"""
        # ── 释放辅助实例 ──
        aux_to_close: list[BrowserInstance] = []
        with self._lock:
            aux_to_close = self._aux_instances.pop(task_id, [])

        # 在锁外关闭辅助实例（避免持锁时做 I/O）
        for inst in aux_to_close:
            try:
                inst.close()
                logger.info(
                    f"[BrowserPool] task={task_id[:8]} 关闭辅助浏览器实例 #{inst.instance_id}"
                )
            except Exception as e:
                logger.warning(
                    f"[BrowserPool] 关闭辅助实例 #{inst.instance_id} 失败: {e}"
                )

        # ── 释放 slot ──
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

        self._prune_idle_slots()

    def close_all(self) -> None:
        """关闭所有浏览器实例（主 slot + 辅助实例，服务关闭时调用）。"""
        with self._lock:
            all_slots = list(self._slots.values())
            self._slots.clear()
            self._task_slot.clear()
            all_aux = []
            for inst_list in self._aux_instances.values():
                all_aux.extend(inst_list)
            self._aux_instances.clear()
        for slot in all_slots:
            slot.instance.close()
        for inst in all_aux:
            try:
                inst.close()
            except Exception:
                pass

    def resize(self, new_max: int) -> None:
        """动态调整池大小（通常在配置变更时调用）。"""
        with self._condition:
            self._max_size = max(1, new_max)
            self._condition.notify_all()
        self._prune_idle_slots()

    @property
    def max_size(self) -> int:
        return self._max_size

    def _should_close_idle_instances(self) -> bool:
        from config import settings

        return bool(getattr(settings, "browser_pool_auto_close_idle", True))

    def _collect_prunable_idle_slot_ids(self) -> list[int]:
        overflow = max(0, len(self._slots) - self._max_size)
        candidates: list[tuple[float, int]] = []
        for sid, slot in self._slots.items():
            if not slot.is_empty:
                continue
            idle_since = slot.idle_since or 0.0
            if self._should_close_idle_instances() or overflow > 0:
                candidates.append((idle_since, sid))

        candidates.sort(key=lambda item: item[0])
        if overflow > 0:
            return [sid for _, sid in candidates[:overflow]]
        if self._should_close_idle_instances():
            return [sid for _, sid in candidates]
        return []

    def _prune_idle_slots(self) -> None:
        idle_instances: list[BrowserInstance] = []
        removed_slot_ids: list[int] = []
        with self._condition:
            for sid in self._collect_prunable_idle_slot_ids():
                slot = self._slots.get(sid)
                if slot is None or not slot.is_empty:
                    continue
                idle_instances.append(slot.instance)
                removed_slot_ids.append(sid)
                self._slots.pop(sid, None)

        for instance in idle_instances:
            instance.close()

        if removed_slot_ids:
            logger.info(
                "[BrowserPool] 已回收空闲 slot: %s",
                ", ".join(f"#{sid}" for sid in removed_slot_ids),
            )

    def status(self) -> dict:
        with self._lock:
            slots_info = []
            alive_main_instances = 0
            for sid, slot in self._slots.items():
                alive = slot.instance.is_alive
                if alive:
                    alive_main_instances += 1
                slots_info.append({
                    "slot_id": sid,
                    "platforms": dict(slot.platforms),
                    "alive": alive,
                })
            aux_instances = [inst for inst_list in self._aux_instances.values() for inst in inst_list]
            aux_count = len(aux_instances)
            alive_aux_instances = sum(1 for inst in aux_instances if inst.is_alive)
            return {
                "max_size": self._max_size,
                "total_slots": len(self._slots),
                "aux_instances": aux_count,
                "alive_aux_instances": alive_aux_instances,
                "alive_main_instances": alive_main_instances,
                "total_instances": len(self._slots) + aux_count,
                "alive_instances": alive_main_instances + alive_aux_instances,
                "slots": slots_info,
            }


# ─── 全局单例 ───────────────────────────────────────────────────────────────

_pool: Optional[BrowserPool] = None
_pool_lock = threading.Lock()


def _cleanup_stale_worker_dirs() -> None:
    """
    清理 ~/.xcrawl-browser-instances/ 下不属于当前进程的旧 worker 目录。

    每次 BrowserPool 初始化时调用，防止历史残留 profile 导致 Chrome 恢复旧标签页。
    只删除非当前进程（worker-<pid>）的目录，保留当前进程自己的目录（由 _reset_profile_dir 管理）。
    """
    current_pid = os.getpid()
    current_worker_dir = _pool_profile_base(pid=current_pid)
    root = Path(_POOL_PROFILE_ROOT)
    if not root.exists():
        return
    removed = 0
    for worker_dir in root.iterdir():
        if not worker_dir.is_dir():
            continue
        if worker_dir.resolve() == Path(current_worker_dir).resolve():
            continue  # 保留当前进程的目录
        try:
            shutil.rmtree(worker_dir, ignore_errors=True)
            removed += 1
        except Exception:
            pass
    if removed > 0:
        logger.info("[BrowserPool] 已清理 %s 个旧 worker profile 目录", removed)


def get_browser_pool() -> BrowserPool:
    """获取全局浏览器实例池（懒初始化，大小由配置决定）。"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                max_size = compute_pool_max_size()
                profile_base = _pool_profile_base()
                cleanup_stale_pool_browsers(base_dir=profile_base)
                _cleanup_stale_worker_dirs()
                _pool = BrowserPool(max_size=max_size)
                logger.info(
                    "[BrowserPool] 初始化，max_size=%s，profile_base=%s",
                    max_size,
                    profile_base,
                )
    return _pool


def is_pool_mode_enabled() -> bool:
    """是否启用浏览器池模式（只要可能出现 2 个及以上并发任务就启用）。"""
    return compute_pool_max_size() > 1
