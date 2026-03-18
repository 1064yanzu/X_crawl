"""
微博多账号池管理模块

功能：
- 存储多个微博账号 Cookie（每个账号独立命名）
- Round Robin 轮询选择账号
- 速率限制时标记账号并跳过
- 线程安全，账号状态变更立即持久化到 ~/.xcrawl-weibo-accounts.json
- 启动时自动从全局 Cookie 文件同步账号

使用方式:
    pool = get_weibo_pool()
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

_DEFAULT_ACCOUNTS_FILE = str(Path.home() / ".xcrawl-weibo-accounts.json")


@dataclass
class WeiboAccountEntry:
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
    rate_reset_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WeiboAccountEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def is_rate_limited(self) -> bool:
        return self.rate_reset_at > time.time()

    @property
    def cookie_count(self) -> int:
        return len(self.cookies)


class WeiboAccountPool:
    """线程安全的微博多账号池"""

    def __init__(self, accounts_file: Optional[str] = None) -> None:
        self._file = Path(accounts_file or _DEFAULT_ACCOUNTS_FILE)
        self._lock = threading.Lock()
        self._accounts: list[WeiboAccountEntry] = []
        self._rr_index: int = 0
        self._load()

    # ─── 持久化 ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._file.exists():
            try:
                with self._file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._accounts = [WeiboAccountEntry.from_dict(d) for d in data]
            except Exception as e:
                logger.error(f"读取微博账号池文件失败: {e}")

        if not self._accounts:
            self._try_sync_from_cookies()

        logger.info(f"已加载微博账号池：{len(self._accounts)} 个账号")

    def _try_sync_from_cookies(self) -> None:
        """启动时自动从全局微博 Cookie 文件同步账号到账号池。"""
        try:
            from crawler.weibo.cookie_manager import (
                load_cookies,
                has_weibo_login,
                _extract_weibo_account_id,
                _group_weibo_cookies_by_account,
            )

            all_cookies = load_cookies()
            if not all_cookies:
                return

            groups = _group_weibo_cookies_by_account(all_cookies)
            for sub_val, group_cookies in groups.items():
                if sub_val == "unknown":
                    continue
                if not has_weibo_login(group_cookies):
                    continue

                alias = f"weibo_{sub_val[:12]}"
                entry = WeiboAccountEntry(
                    account_id=str(uuid.uuid4()),
                    alias=alias,
                    cookies=group_cookies,
                )
                self._accounts.append(entry)
                logger.info(
                    f"微博账号池自动同步：{alias!r}（{len(group_cookies)} 条 Cookie）"
                )

            if self._accounts:
                self._save()

        except Exception as e:
            logger.warning(f"从微博 Cookie 文件自动同步账号失败: {e}")

    def _save(self) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            with self._file.open("w", encoding="utf-8") as f:
                json.dump(
                    [a.to_dict() for a in self._accounts],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"写入微博账号池文件失败: {e}")

    # ─── 账号 CRUD ────────────────────────────────────────────────────────

    def add_account(self, alias: str, cookies: list[dict]) -> WeiboAccountEntry:
        """添加新账号。若 alias 已存在则更新 cookies。"""
        with self._lock:
            for acc in self._accounts:
                if acc.alias == alias:
                    acc.cookies = cookies
                    acc.is_valid = True
                    acc.enabled = True
                    acc.added_at = time.time()
                    self._save()
                    logger.info(f"微博账号 {alias!r} 已更新（{len(cookies)} 条 Cookie）")
                    return acc
            entry = WeiboAccountEntry(
                account_id=str(uuid.uuid4()),
                alias=alias,
                cookies=cookies,
            )
            self._accounts.append(entry)
            self._save()
            logger.info(f"微博账号 {alias!r} 已添加（{len(cookies)} 条 Cookie）")
            return entry

    def remove_account(self, account_id: str) -> bool:
        with self._lock:
            before = len(self._accounts)
            self._accounts = [a for a in self._accounts if a.account_id != account_id]
            if len(self._accounts) < before:
                self._save()
                return True
            return False

    def update_account(
        self, account_id: str, alias: Optional[str] = None, enabled: Optional[bool] = None
    ) -> Optional[WeiboAccountEntry]:
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

    def get_account(self, account_id: str) -> Optional[WeiboAccountEntry]:
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    return acc
            return None

    def list_accounts(self) -> list[WeiboAccountEntry]:
        with self._lock:
            return list(self._accounts)

    # ─── 轮换策略 ─────────────────────────────────────────────────────────

    def pick_account_by_index(self, index: int) -> Optional[WeiboAccountEntry]:
        """按索引选择账号（用于 slot 绑定）。index 对可用账号列表取模。"""
        with self._lock:
            usable = [a for a in self._accounts if a.enabled and a.is_valid]
            if not usable:
                return None
            return usable[index % len(usable)]

    def pick_next_account(
        self, current_account_id: Optional[str] = None
    ) -> Optional[WeiboAccountEntry]:
        """Round Robin 选择下一个可用微博账号。"""
        with self._lock:
            usable = [
                a
                for a in self._accounts
                if a.enabled and a.is_valid and not a.is_rate_limited
            ]
            if not usable:
                if current_account_id:
                    cur = next(
                        (a for a in self._accounts if a.account_id == current_account_id),
                        None,
                    )
                    if cur and cur.enabled:
                        return cur
                return None

            if len(usable) == 1:
                return usable[0]

            current_idx = -1
            for i, a in enumerate(usable):
                if a.account_id == current_account_id:
                    current_idx = i
                    break
            next_idx = (current_idx + 1) % len(usable)
            return usable[next_idx]

    def mark_account_used(self, account_id: str) -> None:
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    acc.last_used_at = time.time()
                    acc.use_count += 1
                    self._save()
                    return

    def mark_account_rate_limited(self, account_id: str, reset_ts: float) -> None:
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    acc.rate_reset_at = reset_ts
                    self._save()
                    logger.warning(
                        f"微博账号 {acc.alias!r} 触发速率限制，"
                        f"重置时间: {time.strftime('%H:%M:%S', time.localtime(reset_ts))}"
                    )
                    return

    def mark_account_invalid(self, account_id: str) -> None:
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    acc.is_valid = False
                    acc.fail_count += 1
                    self._save()
                    logger.warning(f"微博账号 {acc.alias!r} 已标记为无效")
                    return

    def mark_account_validated(self, account_id: str) -> None:
        with self._lock:
            for acc in self._accounts:
                if acc.account_id == account_id:
                    acc.is_valid = True
                    acc.last_validated_at = time.time()
                    self._save()
                    return

    # ─── 统计 ─────────────────────────────────────────────────────────────

    def get_active_account_count(self) -> int:
        with self._lock:
            now = time.time()
            return sum(
                1
                for a in self._accounts
                if a.enabled and a.is_valid and a.rate_reset_at <= now
            )

    def total_count(self) -> int:
        with self._lock:
            return len(self._accounts)


# ─── 单例 ─────────────────────────────────────────────────────────────────────

_pool_instance: Optional[WeiboAccountPool] = None
_pool_lock = threading.Lock()


def get_weibo_pool() -> WeiboAccountPool:
    """获取模块级微博账号池单例"""
    global _pool_instance
    if _pool_instance is None:
        with _pool_lock:
            if _pool_instance is None:
                _pool_instance = WeiboAccountPool()
    return _pool_instance
