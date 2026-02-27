"""跨平台运行时判定与 Linux 无头加固策略。"""
from __future__ import annotations

import os
import sys


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def has_display_server() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def should_force_headless_on_linux(*, browser_headless: bool) -> bool:
    return is_linux() and (not browser_headless) and (not has_display_server())


def linux_headless_args_enabled(*, browser_linux_hardening: bool, browser_headless: bool) -> bool:
    return is_linux() and browser_linux_hardening and browser_headless
