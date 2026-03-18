"""
Cookie ↔ 账号池同步模块

职责：
- 保存 Cookie 时自动识别账号并同步到账号池
- 清除 Cookie 时同步清理账号池中对应账号
- 从 twid Cookie 提取用户 ID 作为账号标识
- 支持多账号：同一文件中可存储多个账号的 cookie，按 twid 分组

原则：
    全局 Cookie 文件是唯一的数据录入入口，
    账号池自动与之保持同步，用户不需要手动添加账号。
"""
import logging
from urllib.parse import unquote

logger = logging.getLogger(__name__)


def extract_user_id(cookies: list[dict]) -> str | None:
    """
    从 twid Cookie 中提取用户 ID。
    twid 格式为 u%3D{user_id}（URL 编码的 u={user_id}）
    """
    for c in cookies:
        if c.get("name") == "twid":
            val = unquote(c.get("value", ""))  # u%3D12345 -> u=12345
            if val.startswith("u="):
                return val[2:]
            return val or None
    return None


def has_login_cookies(cookies: list[dict]) -> bool:
    """检查 Cookie 列表是否包含完整登录凭证"""
    names = {c.get("name", "") for c in cookies}
    return "auth_token" in names and "twid" in names


def group_cookies_by_account(all_cookies: list[dict]) -> dict[str, list[dict]]:
    """
    将所有 cookie 按账号分组。
    
    复用 cookie_manager 中的 _group_cookies_by_user 实现，
    基于 twid 位置就近原则分配 cookie 到对应账号。
    
    Returns:
        {user_id: [cookies], ...}
    """
    from crawler.cookie_manager import _group_cookies_by_user
    return _group_cookies_by_user(all_cookies)


def sync_cookies_to_pool(cookies: list[dict]) -> None:
    """
    将新增 Cookie 同步到账号池。

    逻辑：
    - 从新增 Cookie 中提取用户 ID（通过 twid）
    - 若账号池中已存在同名账号 → 更新 Cookie
    - 若账号池中不存在 → 自动添加
    - 使用 "user_{user_id}" 作为 alias

    此函数在 Cookie 保存/采集后调用。
    """
    if not cookies:
        return

    user_id = extract_user_id(cookies)
    if not user_id:
        logger.debug("新增 Cookie 中未找到 twid，无法识别账号，跳过同步")
        return

    if not has_login_cookies(cookies):
        logger.debug("新增 Cookie 登录态不完整（缺 auth_token/twid），跳过同步")
        return

    try:
        from crawler.account_pool import get_pool

        pool = get_pool()
        alias = f"user_{user_id}"

        # 查找是否已有该账号（按 alias 匹配）
        existing = None
        for acc in pool.list_accounts():
            if acc.alias == alias:
                existing = acc
                break

        if existing:
            # 已存在 → 更新 Cookie
            pool.add_account(alias=alias, cookies=cookies)
            logger.info(f"账号池同步：已更新账号 {alias!r}（{len(cookies)} 条 Cookie）")
        else:
            # 不存在 → 新建
            pool.add_account(alias=alias, cookies=cookies)
            logger.info(f"账号池同步：已自动添加账号 {alias!r}（{len(cookies)} 条 Cookie）")

    except Exception as e:
        # 同步失败不应阻断主流程
        logger.warning(f"Cookie → 账号池同步失败（不影响 Cookie 保存）: {e}")


def sync_all_cookies_to_pool() -> None:
    """
    全量同步：将全局 Cookie 文件中的所有账号同步到账号池。
    用于启动时或手动触发的完整同步。
    """
    try:
        from crawler.cookie_manager import load_cookies
        from crawler.account_pool import get_pool

        all_cookies = load_cookies()
        if not all_cookies:
            logger.debug("全局 Cookie 文件为空，无需同步")
            return

        # 按账号分组
        groups = group_cookies_by_account(all_cookies)
        pool = get_pool()

        for user_id, group_cookies in groups.items():
            if user_id == "unknown":
                logger.debug("跳过无法识别的 Cookie 组（缺 twid）")
                continue

            if not has_login_cookies(group_cookies):
                logger.debug(f"账号 user_{user_id} 的 Cookie 登录态不完整，跳过")
                continue

            alias = f"user_{user_id}"
            existing = None
            for acc in pool.list_accounts():
                if acc.alias == alias:
                    existing = acc
                    break

            if existing:
                pool.add_account(alias=alias, cookies=group_cookies)
                logger.info(f"全量同步：已更新账号 {alias!r}（{len(group_cookies)} 条 Cookie）")
            else:
                pool.add_account(alias=alias, cookies=group_cookies)
                logger.info(f"全量同步：已添加账号 {alias!r}（{len(group_cookies)} 条 Cookie）")

    except Exception as e:
        logger.warning(f"全量同步失败: {e}")


def remove_account_from_pool(cookies: list[dict]) -> None:
    """
    从账号池中移除对应账号（Cookie 被清除时调用）。
    """
    user_id = extract_user_id(cookies)
    if not user_id:
        return

    try:
        from crawler.account_pool import get_pool

        pool = get_pool()
        alias = f"user_{user_id}"

        for acc in pool.list_accounts():
            if acc.alias == alias:
                pool.remove_account(acc.account_id)
                logger.info(f"账号池同步：已移除账号 {alias!r}")
                return

    except Exception as e:
        logger.warning(f"账号池移除失败: {e}")


# ─── 微博 Cookie ↔ 账号池同步 ──────────────────────────────────────────────


def sync_weibo_cookies_to_pool(cookies: list[dict]) -> None:
    """
    将新增微博 Cookie 同步到微博账号池。

    逻辑：
    - 从新增 Cookie 中提取 SUB 值作为账号标识
    - 若账号池中已存在同名账号 → 更新 Cookie
    - 若不存在 → 自动添加
    """
    if not cookies:
        return

    try:
        from crawler.weibo.cookie_manager import _extract_weibo_account_id, has_weibo_login
        from crawler.weibo.account_pool import get_weibo_pool

        sub_val = _extract_weibo_account_id(cookies)
        if sub_val == "unknown":
            logger.debug("微博 Cookie 中未找到 SUB，无法识别账号，跳过同步")
            return

        if not has_weibo_login(cookies):
            logger.debug("微博 Cookie 登录态不完整（缺 SUB），跳过同步")
            return

        pool = get_weibo_pool()
        alias = f"weibo_{sub_val[:12]}"
        pool.add_account(alias=alias, cookies=cookies)
        logger.info(f"微博账号池同步：已同步账号 {alias!r}（{len(cookies)} 条 Cookie）")

    except Exception as e:
        logger.warning(f"微博 Cookie → 账号池同步失败（不影响 Cookie 保存）: {e}")


def sync_all_weibo_cookies_to_pool() -> None:
    """
    全量同步：将全局微博 Cookie 文件中的所有账号同步到微博账号池。
    """
    try:
        from crawler.weibo.cookie_manager import (
            load_cookies,
            has_weibo_login,
            _group_weibo_cookies_by_account,
        )
        from crawler.weibo.account_pool import get_weibo_pool

        all_cookies = load_cookies()
        if not all_cookies:
            logger.debug("全局微博 Cookie 文件为空，无需同步")
            return

        groups = _group_weibo_cookies_by_account(all_cookies)
        pool = get_weibo_pool()

        for sub_val, group_cookies in groups.items():
            if sub_val == "unknown":
                continue
            if not has_weibo_login(group_cookies):
                continue

            alias = f"weibo_{sub_val[:12]}"
            pool.add_account(alias=alias, cookies=group_cookies)
            logger.info(
                f"微博全量同步：已同步账号 {alias!r}（{len(group_cookies)} 条 Cookie）"
            )

    except Exception as e:
        logger.warning(f"微博全量同步失败: {e}")
