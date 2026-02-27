"""
跨平台浏览器自动检测模块
支持 macOS / Windows / Linux
自动检测 Chrome、Edge、Firefox、UC、夸克、Arc、Brave 等主流浏览器
"""
import os
import sys
import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── 浏览器定义 ───────────────────────────────────────────────────────────────

class BrowserDef:
    """单个浏览器的定义：ID、显示名、内核类型及各平台路径"""

    def __init__(
        self,
        browser_id: str,
        name: str,
        engine: str,  # "chromium" | "firefox" | "other"
        paths: dict[str, list[str]],
        user_data: dict[str, list[str]],
        path_commands: list[str] | None = None,
    ):
        self.browser_id = browser_id
        self.name = name
        self.engine = engine
        self.paths = paths              # 各平台候选可执行文件路径
        self.user_data = user_data      # 各平台候选用户数据目录
        self.path_commands = path_commands or []  # PATH 中可搜索的命令名


_home = str(Path.home())

# ── 所有支持的浏览器定义 ─────────────────────────────────────────────────────

BROWSER_DEFINITIONS: list[BrowserDef] = [
    BrowserDef(
        browser_id="chrome",
        name="Google Chrome",
        engine="chromium",
        paths={
            "darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
            "win32": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ],
            "linux": [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/local/bin/google-chrome",
                "/snap/bin/chromium",
            ],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/Google/Chrome"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")],
            "linux": [f"{_home}/.config/google-chrome"],
        },
        path_commands=["google-chrome", "google-chrome-stable", "chrome"],
    ),
    BrowserDef(
        browser_id="chrome_canary",
        name="Google Chrome Canary",
        engine="chromium",
        paths={
            "darwin": ["/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome SxS\Application\chrome.exe")],
            "linux": [],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/Google/Chrome Canary"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome SxS\User Data")],
            "linux": [],
        },
    ),
    BrowserDef(
        browser_id="edge",
        name="Microsoft Edge",
        engine="chromium",
        paths={
            "darwin": ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
            "win32": [
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            ],
            "linux": ["/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable", "/usr/bin/microsoft-edge-dev"],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/Microsoft Edge"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data")],
            "linux": [f"{_home}/.config/microsoft-edge"],
        },
        path_commands=["microsoft-edge", "microsoft-edge-stable", "microsoft-edge-dev"],
    ),
    BrowserDef(
        browser_id="brave",
        name="Brave Browser",
        engine="chromium",
        paths={
            "darwin": ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
            "win32": [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            ],
            "linux": ["/usr/bin/brave-browser", "/usr/bin/brave"],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/BraveSoftware/Brave-Browser"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data")],
            "linux": [f"{_home}/.config/BraveSoftware/Brave-Browser"],
        },
        path_commands=["brave-browser", "brave"],
    ),
    BrowserDef(
        browser_id="arc",
        name="Arc",
        engine="chromium",
        paths={
            "darwin": ["/Applications/Arc.app/Contents/MacOS/Arc"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\Packages\TheBrowserCompany.Arc_*\LocalCache\Local\Arc\Application\arc.exe")],
            "linux": [],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/Arc/User Data"],
            "win32": [],
            "linux": [],
        },
    ),
    BrowserDef(
        browser_id="chromium",
        name="Chromium",
        engine="chromium",
        paths={
            "darwin": ["/Applications/Chromium.app/Contents/MacOS/Chromium"],
            "win32": [],
            "linux": ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/snap/bin/chromium"],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/Chromium"],
            "win32": [],
            "linux": [f"{_home}/.config/chromium"],
        },
        path_commands=["chromium-browser", "chromium"],
    ),
    BrowserDef(
        browser_id="vivaldi",
        name="Vivaldi",
        engine="chromium",
        paths={
            "darwin": ["/Applications/Vivaldi.app/Contents/MacOS/Vivaldi"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe")],
            "linux": ["/usr/bin/vivaldi", "/usr/bin/vivaldi-stable"],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/Vivaldi"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\User Data")],
            "linux": [f"{_home}/.config/vivaldi"],
        },
        path_commands=["vivaldi"],
    ),
    BrowserDef(
        browser_id="opera",
        name="Opera",
        engine="chromium",
        paths={
            "darwin": ["/Applications/Opera.app/Contents/MacOS/Opera"],
            "win32": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
                r"C:\Program Files\Opera\opera.exe",
            ],
            "linux": ["/usr/bin/opera"],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/com.operasoftware.Opera"],
            "win32": [os.path.expandvars(r"%APPDATA%\Opera Software\Opera Stable")],
            "linux": [f"{_home}/.config/opera"],
        },
        path_commands=["opera"],
    ),
    BrowserDef(
        browser_id="uc",
        name="UC Browser",
        engine="chromium",
        paths={
            "darwin": ["/Applications/UCBrowser.app/Contents/MacOS/UCBrowser"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\UCBrowser\Application\UCBrowser.exe")],
            "linux": [],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/UCBrowser"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\UCBrowser\User Data")],
            "linux": [],
        },
    ),
    BrowserDef(
        browser_id="quark",
        name="夸克浏览器 (Quark)",
        engine="chromium",
        paths={
            "darwin": ["/Applications/Quark Browser.app/Contents/MacOS/Quark Browser"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\Quark\Application\Quark.exe")],
            "linux": [],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/Quark Browser"],
            "win32": [os.path.expandvars(r"%LOCALAPPDATA%\Quark\User Data")],
            "linux": [],
        },
    ),
    # ── 非 Chromium 内核（仅展示，不可选用） ──
    BrowserDef(
        browser_id="firefox",
        name="Mozilla Firefox",
        engine="firefox",
        paths={
            "darwin": ["/Applications/Firefox.app/Contents/MacOS/firefox"],
            "win32": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            ],
            "linux": ["/usr/bin/firefox", "/snap/bin/firefox"],
        },
        user_data={
            "darwin": [f"{_home}/Library/Application Support/Firefox"],
            "win32": [os.path.expandvars(r"%APPDATA%\Mozilla\Firefox")],
            "linux": [f"{_home}/.mozilla/firefox"],
        },
        path_commands=["firefox"],
    ),
    BrowserDef(
        browser_id="safari",
        name="Safari",
        engine="other",
        paths={
            "darwin": ["/Applications/Safari.app/Contents/MacOS/Safari"],
            "win32": [],
            "linux": [],
        },
        user_data={
            "darwin": [f"{_home}/Library/Safari"],
            "win32": [],
            "linux": [],
        },
    ),
]


# ── 平台检测 ─────────────────────────────────────────────────────────────────

def _get_platform() -> str:
    """标准化平台标识"""
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform in ("win32", "cygwin"):
        return "win32"
    return sys.platform


# ── 核心检测函数 ──────────────────────────────────────────────────────────────

def _find_exec_path(browser: BrowserDef, platform: str) -> Optional[str]:
    """查找浏览器可执行文件路径"""
    # 1. PATH 中搜索
    for cmd in browser.path_commands:
        path = shutil.which(cmd)
        if path:
            return path

    # 2. 候选路径列表
    for path in browser.paths.get(platform, []):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    return None


def _find_user_data(browser: BrowserDef, platform: str) -> Optional[str]:
    """查找浏览器用户数据目录"""
    for path in browser.user_data.get(platform, []):
        if os.path.isdir(path):
            return path
    return None


def detect_all_browsers() -> list[dict]:
    """
    检测系统中所有已安装的浏览器

    Returns:
        浏览器列表，每项包含：
        - id: 浏览器标识符
        - name: 显示名称
        - engine: 内核类型 ("chromium" | "firefox" | "other")
        - compatible: 是否与 DrissionPage 兼容
        - path: 可执行文件路径
        - user_data_path: 用户数据目录路径（可能为 None）
    """
    platform = _get_platform()
    result = []

    for bdef in BROWSER_DEFINITIONS:
        exec_path = _find_exec_path(bdef, platform)
        if not exec_path:
            continue

        user_data = _find_user_data(bdef, platform)
        result.append({
            "id": bdef.browser_id,
            "name": bdef.name,
            "engine": bdef.engine,
            "compatible": bdef.engine == "chromium",
            "path": exec_path,
            "user_data_path": user_data,
        })

    logger.info(f"检测到 {len(result)} 个已安装浏览器: {[b['name'] for b in result]}")
    return result


# ── 向后兼容函数 ──────────────────────────────────────────────────────────────

def detect_browser_path() -> Optional[str]:
    """
    自动检测系统可用的 Chromium 内核浏览器路径（向后兼容）

    Returns:
        浏览器可执行文件的绝对路径，未找到返回 None
    """
    browsers = detect_all_browsers()
    for b in browsers:
        if b["compatible"]:
            logger.info(f"自动选择兼容浏览器: {b['name']} → {b['path']}")
            return b["path"]

    logger.warning("未自动检测到 Chromium 内核浏览器，请手动配置 BROWSER_EXEC_PATH")
    return None


def detect_user_data_path() -> Optional[str]:
    """
    自动检测浏览器用户数据目录（向后兼容）

    Returns:
        用户数据目录的绝对路径，未找到返回 None
    """
    browsers = detect_all_browsers()
    for b in browsers:
        if b["compatible"] and b["user_data_path"]:
            # 需要包含 Default Profile
            default_profile = os.path.join(b["user_data_path"], "Default")
            if os.path.isdir(default_profile):
                logger.info(f"找到浏览器用户数据目录: {b['user_data_path']}")
                return b["user_data_path"]

    logger.warning("未自动检测到用户数据目录")
    return None


def detect_all() -> dict[str, Optional[str]]:
    """
    检测所有浏览器信息，返回汇总结果（向后兼容）

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


def get_browser_by_id(browser_id: str) -> Optional[dict]:
    """
    根据 ID 查找已安装的浏览器信息

    Returns:
        浏览器信息字典，未找到返回 None
    """
    browsers = detect_all_browsers()
    for b in browsers:
        if b["id"] == browser_id:
            return b
    return None
