"""跨平台运行时判定与 Linux 无头加固策略。"""
from __future__ import annotations

import os
import subprocess
import sys


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def has_display_server() -> bool:
    """检查是否有真实的显示服务器（Xvfb 虚拟显示不算）。"""
    display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if not display:
        return False
    # 如果 DISPLAY 指向 Xvfb 虚拟显示，视为无真实显示服务
    if _is_xvfb_display(display):
        return False
    return True


def _is_xvfb_display(display: str) -> bool:
    """检查指定的 DISPLAY 是否由 Xvfb 提供。"""
    try:
        result = subprocess.run(
            ["pgrep", "-af", f"Xvfb {display}"],
            capture_output=True, text=True, timeout=3,
        )
        return result.returncode == 0 and "Xvfb" in result.stdout
    except Exception:
        return False


def should_force_headless_on_linux(*, browser_headless: bool) -> bool:
    return is_linux() and (not browser_headless) and (not has_display_server())


def linux_headless_args_enabled(*, browser_linux_hardening: bool, browser_headless: bool) -> bool:
    return is_linux() and browser_linux_hardening and browser_headless

