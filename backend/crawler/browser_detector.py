"""
跨平台浏览器自动检测模块
支持 macOS / Windows / Linux
自动检测 Chrome、Edge、Chromium 的可执行文件路径和用户数据目录
"""
import os
import sys
import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 各平台浏览器可执行文件候选路径 ─────────────────────────────────────────────

_BROWSER_PATHS: dict[str, list[str]] = {
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    ],
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        # 用户环境
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ],
    "linux": [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/microsoft-edge",
        "/snap/bin/chromium",
        "/usr/local/bin/google-chrome",
    ],
}

# ── 各平台用户数据目录候选路径 ─────────────────────────────────────────────────

_USER_DATA_PATHS: dict[str, list[str]] = {
    "darwin": [
        str(Path.home() / "Library/Application Support/Google/Chrome"),
        str(Path.home() / "Library/Application Support/Microsoft Edge"),
        str(Path.home() / "Library/Application Support/Chromium"),
        str(Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser"),
    ],
    "win32": [
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"),
    ],
    "linux": [
        str(Path.home() / ".config/google-chrome"),
        str(Path.home() / ".config/chromium"),
        str(Path.home() / ".config/microsoft-edge"),
        str(Path.home() / ".config/BraveSoftware/Brave-Browser"),
    ],
}


def detect_browser_path() -> Optional[str]:
    """
    自动检测系统可用的 Chromium 内核浏览器路径

    检测顺序：PATH 中的 google-chrome → 候选路径列表

    Returns:
        浏览器可执行文件的绝对路径，未找到返回 None
    """
    platform = _get_platform()

    # 1. 先尝试 PATH 中的命令
    for cmd in ("google-chrome", "google-chrome-stable", "chromium-browser",
                "chromium", "microsoft-edge", "brave-browser"):
        path = shutil.which(cmd)
        if path:
            logger.info(f"在 PATH 中找到浏览器: {cmd} → {path}")
            return path

    # 2. 遍历候选路径
    for path in _BROWSER_PATHS.get(platform, []):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            logger.info(f"找到浏览器: {path}")
            return path

    logger.warning("未自动检测到浏览器，请手动配置 BROWSER_EXEC_PATH")
    return None


def detect_user_data_path() -> Optional[str]:
    """
    自动检测浏览器用户数据目录（含登录状态的 Profile）

    Returns:
        用户数据目录的绝对路径，未找到返回 None
    """
    platform = _get_platform()

    for path in _USER_DATA_PATHS.get(platform, []):
        # 判断目录存在且包含 Default Profile（即曾经正常使用过）
        if os.path.isdir(path) and os.path.isdir(os.path.join(path, "Default")):
            logger.info(f"找到浏览器用户数据目录: {path}")
            return path

    logger.warning(
        "未自动检测到用户数据目录（或目录内无 Default Profile），"
        "若要保留登录状态，请手动配置 BROWSER_USER_DATA_PATH"
    )
    return None


def detect_all() -> dict[str, Optional[str]]:
    """
    检测所有浏览器信息，返回汇总结果

    Returns:
        dict with keys: browser_path, user_data_path, platform
    """
    result = {
        "browser_path": detect_browser_path(),
        "user_data_path": detect_user_data_path(),
        "platform": _get_platform(),
    }
    logger.info(f"浏览器检测结果: {result}")
    return result


def _get_platform() -> str:
    """标准化平台标识"""
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform in ("win32", "cygwin"):
        return "win32"
    return sys.platform
