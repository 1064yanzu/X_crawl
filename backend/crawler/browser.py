"""
浏览器管理模块
- 策略零（用户选择）：使用用户在设置界面选择的浏览器启动
- 策略一（推荐）：接管模式 —— 连接用户以 --remote-debugging-port=9222 启动的 Chrome
  优点：完全复用真实浏览器指纹、Cookie、登录状态，无任何冲突风险
- 策略二（回退）：独立 Profile 模式 —— 使用与系统 Chrome 隔离的专用目录启动
  用于用户未开启调试端口时的回退

【推荐使用方式】
关闭所有 Chrome 窗口后，执行：
  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
    --remote-debugging-port=9222 \\
    --user-data-dir="$HOME/Library/Application Support/Google/Chrome"
然后再启动爬虫服务，即可完整复用你的浏览器指纹和登录状态。
"""
import os
import logging
import socket
import subprocess
from pathlib import Path
from typing import Optional
from DrissionPage import Chromium, ChromiumOptions

from config import settings
from crawler.browser_detector import detect_browser_path, get_browser_by_id
from crawler.platform_runtime import (
    should_force_headless_on_linux,
    linux_headless_args_enabled,
)
from crawler.stealth import apply_stealth_to_tab

logger = logging.getLogger(__name__)

_browser: Optional[Chromium] = None

# 爬虫专用独立 Profile 目录（与系统 Chrome 完全隔离）
_CRAWLER_PROFILE_DIR = str(Path.home() / ".xcrawl-browser-profile")


def _is_user_data_locked(user_data_path: str) -> bool:
    """
    检测浏览器用户数据目录是否已被另一个浏览器进程占用。
    
    Chromium 内核浏览器运行时会在用户数据目录下创建 SingletonLock 文件。
    如果该文件存在，说明有另一个 Chrome 实例正在使用该目录，
    此时再用同一目录启动新实例会导致 BrowserConnectError。
    """
    lock_file = os.path.join(user_data_path, "SingletonLock")
    if os.path.exists(lock_file) or os.path.islink(lock_file):
        logger.info(f"检测到锁文件: {lock_file}，该目录正被另一个浏览器进程使用")
        return True
    return False


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """快速检测端口是否有进程在监听"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _pick_free_local_port() -> int:
    """分配一个可用的本地调试端口，避免固定 9222 被占用导致启动失败。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _profile_in_use(user_data_path: str) -> bool:
    """粗略判断是否有 Chrome/Chromium 进程正在使用该 profile。"""
    try:
        escaped = user_data_path.replace("'", "'\''")
        cmd = (
            "ps -ef | grep -E 'chrome|chromium' | grep -v grep | "
            f"grep -F -- '--user-data-dir={escaped}'"
        )
        proc = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True)
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except Exception:
        return False


def _cleanup_stale_singleton_locks(user_data_path: str) -> None:
    """清理孤儿锁文件（仅在确认 profile 未被进程占用时执行）。"""
    lock_names = ("SingletonLock", "SingletonSocket", "SingletonCookie")
    if _profile_in_use(user_data_path):
        logger.info(f"用户数据目录仍被进程占用，跳过锁清理: {user_data_path}")
        return
    removed = []
    for name in lock_names:
        p = os.path.join(user_data_path, name)
        try:
            if os.path.exists(p) or os.path.islink(p):
                os.remove(p)
                removed.append(name)
        except Exception:
            pass
    if removed:
        logger.warning(f"已清理孤儿锁文件 {removed}（profile: {user_data_path}）")


def get_browser() -> Chromium:
    """获取浏览器单例，首次调用时自动初始化"""
    global _browser
    if _browser is None:
        _browser = _create_browser()
    return _browser


def _resolve_browser_paths() -> tuple[Optional[str], Optional[str]]:
    """
    根据用户选择 + 配置项 + 自动检测，解析浏览器可执行文件路径和用户数据目录。

    优先级：
    1. settings.browser_exec_path（手动配置的路径，最高优先级）
    2. settings.browser_selected_id（用户在 UI 中选择的浏览器）
    3. 自动检测（detect_browser_path）

    Returns:
        (exec_path, user_data_path)  任一可能为 None
    """
    # 1. 手动配置优先
    if settings.browser_exec_path:
        logger.info(f"使用手动配置的浏览器路径: {settings.browser_exec_path}")
        return settings.browser_exec_path, settings.browser_user_data_path or None

    # 2. 用户在 UI 选择的浏览器
    selected_id = settings.browser_selected_id
    if selected_id:
        browser_info = get_browser_by_id(selected_id)
        if browser_info and browser_info["compatible"]:
            logger.info(f"使用用户选择的浏览器: {browser_info['name']} ({selected_id})")
            return browser_info["path"], browser_info.get("user_data_path")
        else:
            logger.warning(f"用户选择的浏览器 '{selected_id}' 不可用或不兼容，回退到自动检测")

    # 3. 自动检测
    return detect_browser_path(), None


def _create_browser() -> Chromium:
    debug_port = settings.browser_debug_port  # 默认 9222

    # ── 策略一：接管模式（优先）────────────────────────────────────────────────
    # 若用户已以 --remote-debugging-port 启动 Chrome，直接连接复用真实指纹
    if not settings.browser_user_data_path and _is_port_open("127.0.0.1", debug_port):
        logger.info(f"检测到调试端口 {debug_port} 已开放，尝试接管现有浏览器实例...")
        try:
            co = ChromiumOptions()
            co.set_local_port(debug_port)
            browser = Chromium(co)
            logger.info("成功接管现有浏览器，复用真实指纹和登录状态")
            return browser
        except Exception as e:
            logger.warning(f"接管浏览器失败（{e}），降级使用独立 Profile 模式")

    # ── 策略二：根据用户选择/自动检测启动 ─────────────────────────────────────
    logger.info("未检测到可接管的浏览器，使用独立 Profile 启动...")
    co = ChromiumOptions()

    # 为当前浏览器实例分配独立调试端口，避免固定 9222 被占用时启动失败
    local_port = _pick_free_local_port()
    co.set_local_port(local_port)
    logger.info(f"独立浏览器实例使用调试端口: {local_port}")

    # 解析浏览器路径（用户选择 → 自动检测）
    exec_path, detected_user_data = _resolve_browser_paths()
    if exec_path:
        co.set_browser_path(exec_path)
        logger.info(f"使用浏览器: {exec_path}")

    # 用户数据目录：手动配置 > 用户选择的浏览器自带 > 爬虫专用隔离目录
    # 如果检测到的目录已被另一个浏览器进程占用（存在 SingletonLock），回退到隔离目录
    candidate_user_data = settings.browser_user_data_path or detected_user_data
    if candidate_user_data and _is_user_data_locked(candidate_user_data):
        logger.warning(
            f"用户数据目录 {candidate_user_data} 已被另一个浏览器进程占用，"
            f"回退到爬虫专用隔离目录: {_CRAWLER_PROFILE_DIR}"
        )
        candidate_user_data = None
    user_data = candidate_user_data or _CRAWLER_PROFILE_DIR
    os.makedirs(user_data, exist_ok=True)

    # 专用目录出现孤儿锁文件时自动清理，避免 BrowserConnectError
    if user_data == _CRAWLER_PROFILE_DIR and _is_user_data_locked(user_data):
        _cleanup_stale_singleton_locks(user_data)

    co.set_user_data_path(user_data)
    logger.info(f"使用用户数据目录: {user_data}")

    # 代理
    if settings.browser_proxy:
        co.set_proxy(settings.browser_proxy)
        logger.info(f"使用代理: {settings.browser_proxy}")

    # 无头模式
    effective_headless = bool(settings.browser_headless)
    if should_force_headless_on_linux(browser_headless=effective_headless):
        effective_headless = True
        logger.warning("检测到 Linux 无显示服务，自动启用 headless 模式（可在设置中关闭自动加固）")

    if effective_headless:
        co.headless(True)
        # 显式设置真实 User-Agent，覆盖 HeadlessChrome 默认标识
        # 使用 macOS + Edge 145 UA，与 JS 层 stealth_navigator 档案保持一致
        _REAL_UA = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
        )
        co.set_argument("--user-agent", _REAL_UA)
        logger.info("浏览器运行于无头模式（已覆盖 User-Agent 为 Edge 145 macOS）")

    # 反识别与运行稳定策略
    # 1) 显式窗口尺寸与语言，减少自动化默认指纹
    co.set_argument("--window-size", "1366,860")
    co.set_argument("--lang", "zh-CN,zh,en,en-GB,en-US")
    co.set_argument("--accept-lang", "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6")
    # 2) 尽量降低 webdriver 痕迹（对不同版本 Chromium 生效程度不同）
    co.set_argument("--disable-blink-features", "AutomationControlled")
    co.set_argument("--disable-infobars")
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    need_root_no_sandbox = (os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0)
    if linux_headless_args_enabled(
        browser_linux_hardening=bool(settings.browser_linux_hardening),
        browser_headless=effective_headless,
    ) or need_root_no_sandbox:
        co.set_argument("--no-sandbox")
        co.set_argument("--disable-dev-shm-usage")
        co.set_argument("--disable-gpu")
        co.set_argument("--disable-setuid-sandbox")
        if need_root_no_sandbox and not effective_headless:
            logger.info("检测到 root 身份运行，已启用 no-sandbox 稳定性参数")
        else:
            logger.info("Linux 无头稳定性参数已启用（no-sandbox/dev-shm/gpu/setuid）")

    # 图片加载策略
    co.no_imgs(settings.browser_block_images)
    if settings.browser_block_images:
        logger.info("已启用禁图模式（browser_block_images=True）")

    # 统一加载模式配置
    load_mode = settings.browser_load_mode if settings.browser_load_mode in ("normal", "eager", "none") else "normal"
    co.set_load_mode(load_mode)
    logger.info(f"页面加载模式: {load_mode}")

    co.mute(True)

    logger.info("正在初始化浏览器...")
    browser = Chromium(co)
    logger.info("浏览器初始化成功")
    return browser


def get_new_tab():
    """获取一个新标签页（用于单次爬虫任务）"""
    tab = get_browser().new_tab()
    # 始终注入 stealth 脚本（反检测是基本需求，不应默认关闭）
    apply_stealth_to_tab(tab, enabled=True)
    return tab


def ensure_browser_alive() -> None:
    """检查浏览器单例是否可用，若已失效则重置以便下次 get_browser() 重新创建"""
    global _browser
    if _browser is not None:
        try:
            _browser.latest_tab
        except Exception:
            logger.warning("浏览器实例已失效，重置单例以便重新创建")
            _browser = None


def reset_browser() -> None:
    """关闭并重置浏览器单例，下次 get_browser() 将根据最新设置重新创建。

    用于任务恢复时，确保使用用户最新选择的浏览器。
    如果 quit() 失败（浏览器卡死），将强制杀掉 Chrome 进程并清理锁文件。
    """
    global _browser
    if _browser is not None:
        try:
            _browser.quit()
            logger.info("已关闭旧浏览器实例，将根据最新配置重新创建")
        except Exception as e:
            logger.warning(f"关闭旧浏览器时出错，尝试强制杀进程: {e}")
            _force_kill_chrome()
        finally:
            _browser = None
    else:
        # 即使 _browser 为 None，也清理可能残留的 Chrome 进程
        _force_kill_chrome()


def _force_kill_chrome() -> None:
    """强制杀掉使用爬虫 profile 的 Chrome 进程，并清理锁文件。"""
    try:
        subprocess.run(
            ["pkill", "-9", "-f", f"chrome.*{_CRAWLER_PROFILE_DIR}"],
            capture_output=True, timeout=5,
        )
        logger.info("已强制杀掉残留 Chrome 进程")
    except Exception:
        pass
    _cleanup_stale_singleton_locks(_CRAWLER_PROFILE_DIR)


def close_browser():
    """释放浏览器资源（服务关闭时调用）"""
    global _browser
    if _browser is not None:
        try:
            _browser.quit()
            logger.info("浏览器已关闭")
        except Exception as e:
            logger.warning(f"关闭浏览器时出错: {e}")
        finally:
            _browser = None
