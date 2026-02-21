"""
浏览器管理模块
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
from pathlib import Path
from typing import Optional
from DrissionPage import Chromium, ChromiumOptions

from config import settings
from crawler.browser_detector import detect_browser_path

logger = logging.getLogger(__name__)

_browser: Optional[Chromium] = None

# 爬虫专用独立 Profile 目录（与系统 Chrome 完全隔离）
_CRAWLER_PROFILE_DIR = str(Path.home() / ".xcrawl-browser-profile")


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """快速检测端口是否有进程在监听"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def get_browser() -> Chromium:
    """获取浏览器单例，首次调用时自动初始化"""
    global _browser
    if _browser is None:
        _browser = _create_browser()
    return _browser


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

    # ── 策略二：独立 Profile 启动（回退）─────────────────────────────────────
    # 使用与系统 Chrome 完全隔离的专用目录，避免用户目录冲突
    logger.info("未检测到可接管的浏览器，使用独立 Profile 启动...")
    co = ChromiumOptions()

    # 浏览器可执行文件路径
    exec_path = settings.browser_exec_path or detect_browser_path()
    if exec_path:
        co.set_browser_path(exec_path)
        logger.info(f"使用浏览器: {exec_path}")

    # 用户数据目录：优先使用配置项，否则使用爬虫专用隔离目录
    user_data = settings.browser_user_data_path or _CRAWLER_PROFILE_DIR
    os.makedirs(user_data, exist_ok=True)
    co.set_user_data_path(user_data)
    logger.info(f"使用用户数据目录: {user_data}")

    # 代理
    if settings.browser_proxy:
        co.set_proxy(settings.browser_proxy)
        logger.info(f"使用代理: {settings.browser_proxy}")

    # 无头模式
    if settings.browser_headless:
        co.headless(True)
        logger.info("浏览器运行于无头模式")

    # 性能优化
    co.no_imgs(True)
    co.mute(True)
    co.set_load_mode("eager")

    logger.info("正在初始化浏览器...")
    browser = Chromium(co)
    logger.info("浏览器初始化成功")
    return browser


def get_new_tab():
    """获取一个新标签页（用于单次爬虫任务）"""
    return get_browser().new_tab()


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
