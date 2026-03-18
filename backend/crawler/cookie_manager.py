"""
Cookie 持久化管理模块
- 将 X/Twitter Cookie 存储为本地 JSON 文件
- 支持从多种格式录入：原始 document.cookie 字符串 / JSON 数组
- 线程安全（使用文件写锁）
"""
import json
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 默认 Cookie 存储路径（用户主目录下，跨项目可复用）
_DEFAULT_COOKIES_FILE = str(Path.home() / ".xcrawl-cookies.json")

_lock = threading.Lock()


def get_cookies_file(path: Optional[str] = None) -> Path:
    return Path(path or _DEFAULT_COOKIES_FILE)


# ─── 读取 ──────────────────────────────────────────────────────────────────

def load_cookies(path: Optional[str] = None) -> list[dict]:
    """
    读取持久化 Cookie 列表。
    返回格式：[{"name": "auth_token", "value": "xxx", "domain": ".x.com"}, ...]
    """
    fp = get_cookies_file(path)
    if not fp.exists():
        return []
    try:
        with fp.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        logger.warning("Cookie 文件格式不是列表，已忽略")
        return []
    except Exception as e:
        logger.error(f"读取 Cookie 文件失败: {e}")
        return []


def get_cookie_dict(path: Optional[str] = None) -> dict[str, str]:
    """返回 {name: value} 字典形式，方便快速查找"""
    return {c["name"]: c.get("value", "") for c in load_cookies(path) if c.get("name")}


# ─── 写入 ──────────────────────────────────────────────────────────────────

def _extract_group_user_id(cookies: list[dict]) -> str:
    """
    从一组 cookie 中提取 user_id（通过 twid cookie）。
    整组 cookie 共享同一个 user_id，用于多账号分组。
    """
    from urllib.parse import unquote
    for c in cookies:
        if c.get("name") == "twid":
            val = unquote(c.get("value", ""))
            if val.startswith("u="):
                return val[2:]
            return val or "unknown"
    return "unknown"


def save_cookies(cookies: list[dict], path: Optional[str] = None, merge: bool = True) -> None:
    """
    将 Cookie 列表持久化写入文件。
    
    Args:
        cookies: [{"name": ..., "value": ..., "domain": ...}, ...]
        path: 文件路径（默认 ~/.xcrawl-cookies.json）
        merge: 是否合并模式（True=追加/更新，False=覆盖）
    
    合并模式逻辑（支持多账号）：
    - 先从整组新 cookie 中提取 twid 确定 user_id
    - 按 (user_id, name, domain) 作为唯一键
    - 同账号同名同域的 cookie 会被覆盖，不同账号的 cookie 保留
    """
    fp = get_cookies_file(path)
    with _lock:
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            
            if merge:
                existing = load_cookies(path)
                
                # 从新 cookie 整组提取 user_id（所有 cookie 共享同一 user_id）
                new_user_id = _extract_group_user_id(cookies)
                
                # 从现有 cookie 按账号分组
                existing_groups = _group_cookies_by_user(existing)
                
                # 用新 cookie 覆盖同账号的所有 cookie
                existing_groups[new_user_id] = cookies
                
                # 合并所有账号的 cookie
                merged = []
                for group_cookies in existing_groups.values():
                    merged.extend(group_cookies)
                
                with fp.open("w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False, indent=2)
                logger.info(
                    f"已合并保存账号 {new_user_id} 的 {len(cookies)} 条 Cookie"
                    f"（总计 {len(merged)} 条，{len(existing_groups)} 个账号）到 {fp}"
                )
            else:
                with fp.open("w", encoding="utf-8") as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
                logger.info(f"已覆盖保存 {len(cookies)} 条 Cookie 到 {fp}")
        except Exception as e:
            logger.error(f"写入 Cookie 文件失败: {e}")
            raise


def _group_cookies_by_user(cookies: list[dict]) -> dict[str, list[dict]]:
    """
    将 cookie 列表按账号分组。
    
    策略：先找出所有 twid cookie 确定账号列表和 auth_token 对应关系，
    然后将其他 cookie 通过位置就近原则分配到对应账号。
    
    Returns:
        {user_id: [cookies], ...}
    """
    from urllib.parse import unquote
    
    if not cookies:
        return {}
    
    # 找出所有 twid 的位置和 user_id
    twid_positions: list[tuple[int, str]] = []
    for i, c in enumerate(cookies):
        if c.get("name") == "twid":
            val = unquote(c.get("value", ""))
            uid = val[2:] if val.startswith("u=") else (val or "unknown")
            twid_positions.append((i, uid))
    
    if not twid_positions:
        # 没有 twid，所有 cookie 归为 unknown 组
        return {"unknown": list(cookies)}
    
    if len(twid_positions) == 1:
        # 只有一个账号，所有 cookie 都属于它
        return {twid_positions[0][1]: list(cookies)}
    
    # 多账号：按 twid 位置切割，每个 twid 前后的 cookie 归属最近的 twid
    # 先建立 cookie index -> user_id 的映射
    groups: dict[str, list[dict]] = {}
    for uid in dict(twid_positions).values():
        groups.setdefault(uid, [])
    
    for i, c in enumerate(cookies):
        # 找到最近的 twid
        closest_uid = twid_positions[0][1]
        min_dist = abs(i - twid_positions[0][0])
        for pos, uid in twid_positions:
            dist = abs(i - pos)
            if dist < min_dist:
                min_dist = dist
                closest_uid = uid
        groups[closest_uid].append(c)
    
    return groups


def clear_cookies(path: Optional[str] = None) -> None:
    """清空本地持久化 Cookie"""
    save_cookies([], path, merge=False)
    logger.info("已清空本地 Cookie")


# ─── 格式转换 ──────────────────────────────────────────────────────────────

def parse_cookie_string(raw: str) -> list[dict]:
    """
    解析原始 document.cookie 字符串（如从浏览器控制台复制）
    格式：name1=value1; name2=value2
    返回：[{"name": "name1", "value": "value1", "domain": ".x.com"}, ...]
    """
    cookies = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            name, _, value = part.partition("=")
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".x.com",
            })
    return cookies


def normalize_cookies(data: list[dict] | str) -> list[dict]:
    """
    统一 Cookie 输入格式：
    - 若传入 str，当作 document.cookie 字符串解析
    - 若传入 list，直接使用（确保每项含 name/value）
    """
    if isinstance(data, str):
        return parse_cookie_string(data)
    # 过滤掉无效项
    return [c for c in data if c.get("name") and c.get("value") is not None]


# ─── 注入到浏览器 tab ──────────────────────────────────────────────────────

# X 认证相关的关键 Cookie，必须标记 secure
_SECURE_COOKIES = {"auth_token", "ct0", "twid", "kdt", "_twitter_sess"}


def _build_cookie_dict(c: dict) -> dict:
    """
    从持久化 Cookie 记录构建完整的 Cookie 字典，
    确保包含所有必要属性（path, secure, httpOnly）。
    X 的认证 Cookie 必须标记 secure=True，否则浏览器不会在 HTTPS 请求中发送。
    """
    name = c.get("name", "")
    domain = c.get("domain", ".x.com")
    path = c.get("path", "/")

    # 如果持久化文件中保存了 secure 属性，使用保存的值；
    # 否则根据是否为关键认证 Cookie 自动判断
    secure = c.get("secure")
    if secure is None or (name in _SECURE_COOKIES and not secure):
        secure = name in _SECURE_COOKIES

    http_only = c.get("httpOnly", name in _SECURE_COOKIES)

    cookie_dict = {
        "name": name,
        "value": c.get("value", ""),
        "domain": domain,
        "path": path,
        "secure": secure,
    }
    if http_only:
        cookie_dict["httpOnly"] = True

    return cookie_dict


def inject_cookies_to_tab(tab, path: Optional[str] = None) -> int:
    """
    将持久化 Cookie 注入到 DrissionPage tab。
    注入前会自动确保浏览器在 x.com 域下（否则 Cookie 无法绑定到该域）。
    返回注入的 Cookie 数量。
    """
    cookies = load_cookies(path)
    if not cookies:
        logger.debug("无持久化 Cookie，跳过注入")
        return 0

    # 确保在目标域下，否则 set.cookies 可能无法正确绑定到 x.com
    try:
        current_url = tab.url or ""
        if "x.com" not in current_url and "twitter.com" not in current_url:
            logger.debug("当前页面非 x.com，先导航到 x.com 以便注入 Cookie")
            tab.get("https://x.com", timeout=15)
    except Exception as e:
        logger.warning(f"导航到 x.com 失败（将继续尝试注入）: {e}")

    injected = 0
    for c in cookies:
        name = c.get("name")
        if not name:
            continue
        try:
            cookie_dict = _build_cookie_dict(c)
            tab.set.cookies(cookie_dict)
            injected += 1
        except Exception as e:
            logger.warning(f"注入 Cookie {name} 失败: {e}")

    logger.info(f"已注入 {injected} 条持久化 Cookie")
    return injected


# ─── 从浏览器 tab 回写 ─────────────────────────────────────────────────────

def capture_cookies_from_tab(tab, path: Optional[str] = None) -> list[dict]:
    """
    从 DrissionPage tab 采集当前 Cookie 并持久化。
    返回采集到的 Cookie 列表。
    """
    try:
        raw = tab.cookies()  # 返回 list[dict]（DrissionPage ≥ 4.x）
    except Exception as e:
        logger.error(f"从浏览器采集 Cookie 失败: {e}")
        return []

    # DrissionPage 返回的格式可能字段各异，统一规范化
    cookies = []
    for c in raw:
        if isinstance(c, dict) and c.get("name"):
            cookies.append({
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": c.get("domain", ".x.com"),
                "path": c.get("path", "/"),
                "secure": c.get("secure", False),
                "httpOnly": c.get("httpOnly", False),
            })

    if cookies:
        save_cookies(cookies, path)
        logger.info(f"已从浏览器采集并保存 {len(cookies)} 条 Cookie")

    return cookies
