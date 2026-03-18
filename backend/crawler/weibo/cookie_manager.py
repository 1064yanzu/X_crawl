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


def _extract_weibo_account_id(cookies: list[dict]) -> str:
    """
    从一组微博 cookie 中提取账号标识（SUB 值）。
    整组 cookie 共享同一个账号标识。
    """
    for c in cookies:
        if c.get("name") == "SUB":
            return c.get("value", "unknown")
    return "unknown"


def _group_weibo_cookies_by_account(cookies: list[dict]) -> dict[str, list[dict]]:
    """
    将微博 cookie 列表按账号分组。
    
    策略：先找出所有 SUB cookie 确定账号列表，
    然后将其他 cookie 通过位置就近原则分配到对应账号。
    
    Returns:
        {sub_value: [cookies], ...}
    """
    if not cookies:
        return {}
    
    # 找出所有 SUB 的位置和值
    sub_positions: list[tuple[int, str]] = []
    for i, c in enumerate(cookies):
        if c.get("name") == "SUB":
            sub_val = c.get("value", "unknown")
            sub_positions.append((i, sub_val))
    
    if not sub_positions:
        return {"unknown": list(cookies)}
    
    if len(sub_positions) == 1:
        return {sub_positions[0][1]: list(cookies)}
    
    # 多账号：按 SUB 位置切割，每个 cookie 归属最近的 SUB
    groups: dict[str, list[dict]] = {}
    for _, sub_val in sub_positions:
        groups.setdefault(sub_val, [])
    
    for i, c in enumerate(cookies):
        closest_sub = sub_positions[0][1]
        min_dist = abs(i - sub_positions[0][0])
        for pos, sub_val in sub_positions:
            dist = abs(i - pos)
            if dist < min_dist:
                min_dist = dist
                closest_sub = sub_val
        groups[closest_sub].append(c)
    
    return groups


def save_cookies(cookies: list[dict], merge: bool = True) -> None:
    """
    持久化 Cookie 列表到磁盘。
    
    Args:
        cookies: Cookie 列表
        merge: 是否合并模式（True=追加/更新，False=覆盖）
    
    合并模式逻辑（支持多账号）：
    - 先从整组新 cookie 中提取 SUB 值确定账号标识
    - 同账号的 cookie 整组替换，不同账号的 cookie 保留
    """
    try:
        if merge:
            existing = load_cookies()
            
            # 从新 cookie 整组提取账号标识
            new_account_id = _extract_weibo_account_id(cookies)
            
            # 从现有 cookie 按账号分组
            existing_groups = _group_weibo_cookies_by_account(existing)
            
            # 用新 cookie 整组替换同账号的 cookie
            existing_groups[new_account_id] = cookies
            
            # 合并所有账号的 cookie
            merged = []
            for group_cookies in existing_groups.values():
                merged.extend(group_cookies)
            
            WEIBO_COOKIES_PATH.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info(
                f"已合并保存微博账号 {new_account_id[:16]}... 的 {len(cookies)} 条 Cookie"
                f"（总计 {len(merged)} 条，{len(existing_groups)} 个账号）"
            )
        else:
            # 覆盖模式（用于清空）
            WEIBO_COOKIES_PATH.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info(f"已覆盖保存 {len(cookies)} 条微博 Cookie")
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
