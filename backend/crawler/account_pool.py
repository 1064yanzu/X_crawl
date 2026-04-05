"""
多账号池管理模块

功能：
- 存储多个 X/Twitter 账号 Cookie（每个账号独立命名）
- Round Robin 轮询选择账号
- 速率限制时标记账号并跳过
- 根据活跃账号数动态计算最优间隔
- 线程安全，账号状态变更立即持久化到 ~/.xcrawl-accounts.json

使用方式:
    pool = get_pool()
    account = pool.pick_next_account()
    if account:
        pool.mark_account_used(account.account_id)
"""
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_ACCOUNTS_FILE = str(Path.home() / ".xcrawl-accounts.json")

# X 平台速率限制窗口（秒）和请求上限（与 rate_tracker 保持一致）
_ENDPOINT_CONFIG = {
    "search":       {"window": 900, "limit": 50},
    "tweet_detail": {"window": 900, "limit": 150},
}

# 安全系数：单账号适度激进(0.80)，多账号有天然错峰更激进(0.72)
_SAFETY_SINGLE = 0.80
_SAFETY_MULTI = 0.72


@dataclass
class AccountEntry:
    account_id: str
    alias: str
    cookies: list[dict]
    enabled: bool = True
    added_at: float = field(default_factory=time.time)
    last_used_at: float = 0.0
    last_validated_at: float = 0.0
    is_valid: bool = True
    use_count: int = 0
    fail_count: int = 0
    rate_reset_at: float = 0.0   # 被限速时记录 reset 时间戳

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AccountEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def is_rate_limited(self) -> bool:
        """是否当前处于速率限制状态"""
        return self.rate_reset_at > time.time()

    @property
    def cookie_count(self) -> int:
        return len(self.cookies)

    @property
    def cookie_domains(self) -> list[str]:
        """返回去重后的 Cookie domain 列表（脱敏用）"""
        return list({c.get("domain", ".x.com") for c in self.cookies})


class AccountPool:
    """线程安全的多账号池"""

    def __init__(self, accounts_file: Optional[str] = None) -> None:
        self._file = Path(accounts_file or _DEFAULT_ACCOUNTS_FILE)
        self._lock = threading.Lock()
        self._accounts: list[AccountEntry] = []
        self._rr_index: int = 0  # Round Robin 指针
        self._load()

    # ─── 持久化 ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        """从文件加载账号列表（启动时调用）"""
        if self._file.exists():
            try:
                with self._file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._accounts = [AccountEntry.from_dict(d) for d in data]
            except Exception as e:
                logger.error(f"读取账号池文件失败: {e}")

        # 如果账号池为空，尝试从全局 Cookie 文件自动同步
        if not self._accounts:
            self._try_sync_from_cookies()

        logger.info(f"已加载账号池：{len(self._accounts)} 个账号")

    def _try_sync_from_cookies(self) -> None:
        """
        启动时自动从全局 Cookie 文件同步账号到账号池。
        确保 Cookie 文件中的有效账号不会因为账号池文件丢失而被遗漏。

        注意：不能调用 sync_cookies_to_pool()，因为它内部通过 get_pool()
        获取单例，而此时单例尚未完成初始化，_pool_lock 可能正被持有，会导致死锁。
        因此这里直接内联同步逻辑。
        """
        try:
            from crawler.cookie_manager import load_cookies
            from crawler.cookie_account_sync import extract_user_id, has_login_cookies

            cookies = load_cookies()
            if not cookies:
                return

            user_id = extract_user_id(cookies)
            if not user_id:
                logger.debug("Cookie 文件中未找到 twid，无法自动同步账号")
                return

            if not has_login_cookies(cookies):
                logger.debug("Cookie 登录态不完整（缺 auth_token/twid），跳过自动同步")
                return

            alias = f"user_{user_id}"
            logger.info(f"账号池为空，从 Cookie 文件自动同步账号 {alias!r}（{len(cookies)} 条 Cookie）...")

            # 直接创建 AccountEntry 并写入文件（绕开单例）
            entry = AccountEntry(
                account_id=str(uuid.uuid4()),
                alias=alias,
                cookies=cookies,
            )
            self._accounts.append(entry)
            self._save()

        except Exception as e:
            logger.warning(f"从 Cookie 文件自动同步账号失败（不影响正常启动）: {e}")

    def _save(self) -> None:
        """持久化当前账号列表（必须在锁内调用）"""
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            with self._file.open("w", encoding="utf-8") as f:
                json.dump([a.to_dict() for a in self._accounts], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"写入账号池文件失败: {e}")

    def reload(self) -> None:
        """从文件重新加载账号列表（运行时热刷新）"""
        with self._lock:
            self._accounts = []
            self._rr_index = 0
            self._load()

    def reset_account_valid(self, account_id: str) -> bool:
        """将账号恢复为完全可用状态（is_valid=True, enabled=True, fail_count=0）"""
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    acc.is_valid = True
                    acc.enabled = True
                    acc.fail_count = 0
                    self._save()
                    logger.info(f"账号 {acc.alias!r} 已恢复为有效并启用")
                    return True
            return False

    # ─── 账号 CRUD ────────────────────────────────────────────────────────

    def add_account(self, alias: str, cookies: list[dict]) -> AccountEntry:
        """添加新账号。若 alias 已存在则更新 cookies。"""
        with self._lock:
            # 查找已有同名账号
            for acc in self._accounts:
                if acc.alias == alias:
                    acc.cookies = cookies
                    acc.is_valid = True
                    acc.enabled = True
                    acc.added_at = time.time()
                    self._save()
                    logger.info(f"账号 {alias!r} 已更新（{len(cookies)} 条 Cookie）")
                    return acc
            # 新增
            entry = AccountEntry(
                account_id=str(uuid.uuid4()),
                alias=alias,
                cookies=cookies,
            )
            self._accounts.append(entry)
            self._save()
            logger.info(f"账号 {alias!r} 已添加（{len(cookies)} 条 Cookie）")
            return entry

    def remove_account(self, account_id: str) -> bool:
        """删除账号，返回是否成功"""
        with self._lock:
            before = len(self._accounts)
            self._accounts = [a for a in self._accounts if a.account_id != account_id]
            if len(self._accounts) < before:
                self._save()
                return True
            return False

    def update_account(self, account_id: str, alias: Optional[str] = None, enabled: Optional[bool] = None) -> Optional[AccountEntry]:
        """更新账号的 alias / enabled 字段"""
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    if alias is not None:
                        acc.alias = alias
                    if enabled is not None:
                        acc.enabled = enabled
                    self._save()
                    return acc
            return None

    def get_account(self, account_id: str) -> Optional[AccountEntry]:
        """按 ID 查找账号（返回副本）"""
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    return acc
            return None

    def list_accounts(self) -> list[AccountEntry]:
        """返回所有账号列表的浅拷贝"""
        with self._lock:
            return list(self._accounts)

    def get_all_accounts(self) -> list[AccountEntry]:
        """
        兼容旧调用方的别名接口。

        早期代码使用 `get_all_accounts()`，后续主接口收敛为 `list_accounts()`。
        这里保留兼容，避免旧链路在运行时直接崩溃。
        """
        return self.list_accounts()

    # ─── 轮换策略 ─────────────────────────────────────────────────────────

    def pick_account_by_index(self, index: int) -> Optional[AccountEntry]:
        """按索引选择账号（用于 slot 绑定）。index 对可用账号列表取模。"""
        with self._lock:
            usable = [a for a in self._accounts if a.enabled and a.is_valid]
            if not usable:
                return None
            return usable[index % len(usable)]

    def pick_next_account(self, current_account_id: Optional[str] = None) -> Optional[AccountEntry]:
        """
        Round Robin 选择下一个可用账号。
        跳过 enabled=False 和 rate_reset_at > now 的账号。
        若无其他可用账号，回退到当前账号（若当前也不可用则返回 None）。
        """
        with self._lock:
            usable = [
                a for a in self._accounts
                if a.enabled and a.is_valid and not a.is_rate_limited
            ]
            if not usable:
                # 尝试回退到当前账号
                if current_account_id:
                    cur = next((a for a in self._accounts if a.account_id == current_account_id), None)
                    if cur and cur.enabled:
                        return cur
                return None

            if len(usable) == 1:
                return usable[0]

            # Round Robin：找到当前账号在 usable 中的位置，取下一个
            current_idx = -1
            for i, a in enumerate(usable):
                if a.account_id == current_account_id:
                    current_idx = i
                    break
            next_idx = (current_idx + 1) % len(usable)
            return usable[next_idx]

    def mark_account_used(self, account_id: str) -> None:
        """标记账号被使用（更新 last_used_at 和 use_count）"""
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    acc.last_used_at = time.time()
                    acc.use_count += 1
                    self._save()
                    return

    def mark_account_rate_limited(self, account_id: str, reset_ts: float) -> None:
        """标记账号被速率限制，记录 reset 时间戳"""
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    acc.rate_reset_at = reset_ts
                    self._save()
                    logger.warning(
                        f"账号 {acc.alias!r} 触发速率限制，"
                        f"重置时间: {time.strftime('%H:%M:%S', time.localtime(reset_ts))}"
                    )
                    return

    def mark_account_invalid(self, account_id: str) -> None:
        """标记账号登录状态无效"""
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    acc.is_valid = False
                    acc.fail_count += 1
                    self._save()
                    logger.warning(f"账号 {acc.alias!r} 已标记为无效（登录失败）")
                    return

    def mark_account_validated(self, account_id: str) -> None:
        """验证成功后更新状态"""
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    acc.is_valid = True
                    acc.last_validated_at = time.time()
                    self._save()
                    return

    # ─── 统计 ─────────────────────────────────────────────────────────────

    def get_active_account_count(self) -> int:
        """返回 enabled=True 且未被限速的账号数"""
        with self._lock:
            now = time.time()
            return sum(
                1 for a in self._accounts
                if a.enabled and a.is_valid and a.rate_reset_at <= now
            )

    def total_count(self) -> int:
        with self._lock:
            return len(self._accounts)


# ─── 动态间隔计算 ─────────────────────────────────────────────────────────────


def compute_dynamic_interval(endpoint: str) -> tuple[float, float, float]:
    """
    根据当前活跃账号数动态计算最优页面间隔。

    原理：
        safe_interval = window / limit / active_count * safety_factor
        多账号时有天然错峰效应，安全系数可适当降低。

    并发模式下（多账号各任务独占），每个账号的请求频率独立计算，
    间隔进一步缩短以提高吞吐。

    Returns:
        (min_sec, max_sec, safety_factor)
    """
    cfg = _ENDPOINT_CONFIG.get(endpoint, {"window": 900, "limit": 50})
    window = cfg["window"]
    limit = cfg["limit"]

    active_count = max(1, get_pool().get_active_account_count())
    safety_factor = _SAFETY_MULTI if active_count > 1 else _SAFETY_SINGLE
    safe_interval = window / limit / active_count * safety_factor

    # 并发模式下每个任务独占一个账号，频率由该账号单独承担，
    # 不需要除以 active_count（已在上面除过了），但可以更激进地缩短区间
    min_sec = safe_interval * 0.55
    max_sec = safe_interval * 0.85
    return min_sec, max_sec, safety_factor


# ─── 单例 ─────────────────────────────────────────────────────────────────────

_pool_instance: Optional[AccountPool] = None
_pool_lock = threading.Lock()


def get_pool() -> AccountPool:
    """获取模块级账号池单例"""
    global _pool_instance
    if _pool_instance is None:
        with _pool_lock:
            if _pool_instance is None:
                _pool_instance = AccountPool()
    return _pool_instance
