"""
微博 Cookie 管理：加载、保存、格式化、注入、捕获。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

WEIBO_COOKIES_PATH = Path.home() / ".xcrawl-weibo-cookies.json"


def load_cookies() -> list[dict]:
    """从磁盘加载 Cookie 列表。"""
    if not WEIBO_COOKIES_PATH.exists():
        return []
    try:
        data = json.loads(WEIBO_COOKIES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"加载微博 Cookie 失败: {e}")
        return []


def save_cookies(cookies: list[dict]) -> None:
    """持久化 Cookie 列表到磁盘。"""
    try:
        WEIBO_COOKIES_PATH.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"保存微博 Cookie 失败: {e}")


def clear_cookies() -> None:
    """清空已保存的 Cookie。"""
    if WEIBO_COOKIES_PATH.exists():
        WEIBO_COOKIES_PATH.unlink()


def normalize_cookies(raw: list[dict] | str) -> list[dict]:
    """
    支持两种输入格式：
    1. JSON 数组 [{name, value, ...}, ...]
    2. 字符串 "key=val; key2=val2"
    统一输出为 [{name, value, domain, path}, ...] 格式。
    """
    if isinstance(raw, str):
        cookies = []
        for pair in raw.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            key, _, value = pair.partition("=")
            cookies.append(
                {
                    "name": key.strip(),
                    "value": value.strip(),
                    "domain": ".weibo.com",
                    "path": "/",
                }
            )
        return cookies

    result = []
    for item in raw:
        # 保留所有原始字段（httpOnly, secure, sameSite 等），只补全缺失字段
        entry = dict(item)
        entry.setdefault("name", "")
        entry.setdefault("value", "")
        entry.setdefault("domain", ".weibo.com")
        entry.setdefault("path", "/")
        result.append(entry)
    return result


def inject_cookies_to_tab(tab, cookies: list[dict]) -> None:
    """将 Cookie 注入到浏览器 tab。"""
    try:
        tab.set.cookies(cookies)
    except Exception as e:
        logger.warning(f"注入微博 Cookie 失败: {e}")


def get_xsrf_token_from_tab(tab) -> Optional[str]:
    """从浏览器 tab 的 Cookie 中提取 XSRF-TOKEN。"""
    try:
        for cookie in tab.cookies():
            name = cookie.get("name", "") if isinstance(cookie, dict) else getattr(cookie, "name", "")
            if name == "XSRF-TOKEN":
                return cookie.get("value", "") if isinstance(cookie, dict) else getattr(cookie, "value", "")
    except Exception as e:
        logger.warning(f"获取 XSRF-TOKEN 失败: {e}")
    return None


def capture_cookies_from_tab(tab) -> list[dict]:
    """从浏览器 tab 捕获域名包含 weibo 的 Cookie。"""
    result = []
    try:
        for cookie in tab.cookies():
            domain = (
                cookie.get("domain", "")
                if isinstance(cookie, dict)
                else getattr(cookie, "domain", "")
            )
            if "weibo" in domain:
                if isinstance(cookie, dict):
                    result.append(cookie)
                else:
                    result.append(
                        {
                            "name": getattr(cookie, "name", ""),
                            "value": getattr(cookie, "value", ""),
                            "domain": domain,
                            "path": getattr(cookie, "path", "/"),
                        }
                    )
    except Exception as e:
        logger.warning(f"捕获微博 Cookie 失败: {e}")
    return result


def has_weibo_login(cookies: list[dict]) -> bool:
    """检查是否有 SUB cookie（微博登录凭证）。"""
    for cookie in cookies:
        name = cookie.get("name", "")
        if name == "SUB":
            return True
    return False
