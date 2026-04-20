"""
YouTube API Key 池（线程安全）。

职责：
- 启动时从 SQLite 加载 Key 列表
- 提供 pick_available(cost) 返回成本可承担的 Key，跳过已禁用/已耗尽/失效的 Key
- 记录配额消耗（record_usage）并在持久化层同步
- 每日太平洋时间重置（reset_expired_quotas，惰性触发）
- 外部变更（CRUD）通过此模块透写，避免 API 路由直接操作数据库

对外暴露：
- get_pool() 单例
- KeyPoolExhausted 异常
- YouTubeApiKey dataclass
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from api.services import youtube_key_db

from . import quota_tracker

logger = logging.getLogger(__name__)


class KeyPoolExhausted(Exception):
    """所有可用 Key 配额已耗尽。"""

    def __init__(self, message: str, reset_at: Optional[str] = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


class NoKeyAvailable(Exception):
    """Key 池为空或全部被禁用 / 失效。"""


@dataclass
class YouTubeApiKey:
    key_id: str
    alias: str
    api_key: str
    enabled: bool = True
    daily_quota_limit: int = quota_tracker.DAILY_QUOTA_DEFAULT
    quota_used_today: int = 0
    quota_reset_at: Optional[str] = None
    status: str = "active"  # active | exhausted | invalid
    last_used_at: Optional[str] = None
    last_validated_at: Optional[str] = None
    fail_count: int = 0
    last_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def remaining(self) -> int:
        return max(0, int(self.daily_quota_limit) - int(self.quota_used_today))

    def can_afford(self, cost: int) -> bool:
        if not self.enabled or self.status != "active":
            return False
        return self.remaining() >= cost

    def to_public_dict(self) -> dict:
        """对外暴露视图：API Key 脱敏。"""
        masked = _mask_key(self.api_key)
        return {
            "key_id": self.key_id,
            "alias": self.alias,
            "api_key_masked": masked,
            "enabled": self.enabled,
            "daily_quota_limit": self.daily_quota_limit,
            "quota_used_today": self.quota_used_today,
            "quota_remaining": self.remaining(),
            "quota_reset_at": self.quota_reset_at,
            "status": self.status,
            "last_used_at": self.last_used_at,
            "last_validated_at": self.last_validated_at,
            "fail_count": self.fail_count,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 10:
        return "****"
    return f"{api_key[:6]}…{api_key[-4:]}"


def _from_row(row: dict) -> YouTubeApiKey:
    return YouTubeApiKey(
        key_id=str(row.get("key_id") or ""),
        alias=str(row.get("alias") or ""),
        api_key=str(row.get("api_key") or ""),
        enabled=bool(row.get("enabled", False)),
        daily_quota_limit=int(row.get("daily_quota_limit") or quota_tracker.DAILY_QUOTA_DEFAULT),
        quota_used_today=int(row.get("quota_used_today") or 0),
        quota_reset_at=row.get("quota_reset_at"),
        status=str(row.get("status") or "active"),
        last_used_at=row.get("last_used_at"),
        last_validated_at=row.get("last_validated_at"),
        fail_count=int(row.get("fail_count") or 0),
        last_error=row.get("last_error"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


class YouTubeApiKeyPool:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._keys: dict[str, YouTubeApiKey] = {}
        self._rr_index = 0
        self._loaded = False

    # ── 加载与重载 ────────────────────────────────────────────────────────

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._reload_locked()
            self._loaded = True

    def reload(self) -> None:
        with self._lock:
            self._reload_locked()

    def _reload_locked(self) -> None:
        rows = youtube_key_db.list_all_keys()
        self._keys = {row["key_id"]: _from_row(row) for row in rows}
        logger.info("YouTube Key 池加载完成：共 %d 个", len(self._keys))

    # ── 查询 ─────────────────────────────────────────────────────────────

    def list_keys(self) -> list[YouTubeApiKey]:
        self.ensure_loaded()
        with self._lock:
            return list(self._keys.values())

    def get(self, key_id: str) -> Optional[YouTubeApiKey]:
        self.ensure_loaded()
        with self._lock:
            return self._keys.get(key_id)

    # ── 配额选择 ────────────────────────────────────────────────────────

    def pick_available(self, cost: int) -> YouTubeApiKey:
        """按 round-robin 返回可承担 cost 的 Key，全部不够则抛出异常。"""
        self.ensure_loaded()
        self._maybe_reset_expired()
        with self._lock:
            active_keys = [k for k in self._keys.values() if k.enabled and k.status != "invalid"]
            if not active_keys:
                raise NoKeyAvailable("未配置任何可用的 YouTube API Key")

            usable = [k for k in active_keys if k.can_afford(cost)]
            if not usable:
                earliest_reset = _earliest_reset(active_keys)
                raise KeyPoolExhausted(
                    f"所有 YouTube API Key 当日配额不足以完成一次调用（至少需要 {cost} 单位）",
                    reset_at=earliest_reset,
                )

            # round-robin 在 usable 内取下一项
            if self._rr_index >= len(usable):
                self._rr_index = 0
            picked = usable[self._rr_index % len(usable)]
            self._rr_index = (self._rr_index + 1) % len(usable)
            return picked

    def record_usage(self, key_id: str, *, cost: int) -> None:
        self.ensure_loaded()
        now_iso = datetime.now(timezone.utc).isoformat()
        new_status: Optional[str] = None
        with self._lock:
            key = self._keys.get(key_id)
            if not key:
                return
            key.quota_used_today += int(cost)
            key.last_used_at = now_iso
            key.fail_count = 0
            if key.remaining() <= 0:
                key.status = "exhausted"
                new_status = "exhausted"
            key.updated_at = now_iso

        youtube_key_db.update_key(
            key_id,
            {
                "quota_used_today": self._keys[key_id].quota_used_today,
                "last_used_at": now_iso,
                "fail_count": 0,
                "status": new_status or self._keys[key_id].status,
            },
        )

    def mark_exhausted(self, key_id: str, *, reset_at: Optional[str] = None) -> None:
        self._mark_status(
            key_id,
            status="exhausted",
            error="quota_exceeded",
            extra_updates={"quota_reset_at": reset_at} if reset_at else {},
        )

    def mark_invalid(self, key_id: str, *, reason: str) -> None:
        self._mark_status(key_id, status="invalid", error=reason)

    def record_failure(self, key_id: str, *, reason: str) -> None:
        self.ensure_loaded()
        now_iso = datetime.now(timezone.utc).isoformat()
        updates: dict = {"last_error": reason, "updated_at": now_iso}
        with self._lock:
            key = self._keys.get(key_id)
            if not key:
                return
            key.fail_count += 1
            key.last_error = reason
            key.updated_at = now_iso
            updates["fail_count"] = key.fail_count
        youtube_key_db.update_key(key_id, updates)

    def mark_validated(self, key_id: str) -> None:
        self.ensure_loaded()
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            key = self._keys.get(key_id)
            if not key:
                return
            key.last_validated_at = now_iso
            key.fail_count = 0
            key.last_error = None
            if key.status == "invalid":
                key.status = "active"
            key.updated_at = now_iso
        youtube_key_db.update_key(
            key_id,
            {
                "last_validated_at": now_iso,
                "fail_count": 0,
                "last_error": None,
                "status": self._keys[key_id].status,
            },
        )

    def _mark_status(
        self,
        key_id: str,
        *,
        status: str,
        error: Optional[str] = None,
        extra_updates: Optional[dict] = None,
    ) -> None:
        self.ensure_loaded()
        now_iso = datetime.now(timezone.utc).isoformat()
        updates: dict = {"status": status, "updated_at": now_iso}
        if error is not None:
            updates["last_error"] = error
        if extra_updates:
            updates.update(extra_updates)
        with self._lock:
            key = self._keys.get(key_id)
            if not key:
                return
            key.status = status
            if error is not None:
                key.last_error = error
            for field_name, value in (extra_updates or {}).items():
                setattr(key, field_name, value)
            key.updated_at = now_iso
        youtube_key_db.update_key(key_id, updates)

    # ── CRUD ─────────────────────────────────────────────────────────────

    def add_key(self, *, alias: str, api_key: str, enabled: bool = True) -> YouTubeApiKey:
        if not api_key or not api_key.strip():
            raise ValueError("API Key 不能为空")
        reset_at = quota_tracker.compute_next_pt_midnight().isoformat()
        row = youtube_key_db.insert_key(
            alias=alias or f"Key-{int(time.time())}",
            api_key=api_key,
            enabled=enabled,
            quota_reset_at=reset_at,
        )
        new_key = _from_row(row)
        with self._lock:
            self._keys[new_key.key_id] = new_key
        return new_key

    def update_key(
        self,
        key_id: str,
        *,
        alias: Optional[str] = None,
        enabled: Optional[bool] = None,
        daily_quota_limit: Optional[int] = None,
    ) -> Optional[YouTubeApiKey]:
        updates: dict = {}
        if alias is not None:
            updates["alias"] = alias.strip() or None
        if enabled is not None:
            updates["enabled"] = enabled
        if daily_quota_limit is not None:
            updates["daily_quota_limit"] = max(1, int(daily_quota_limit))
        if not updates:
            return self.get(key_id)
        row = youtube_key_db.update_key(key_id, updates)
        if not row:
            return None
        updated = _from_row(row)
        with self._lock:
            self._keys[key_id] = updated
        return updated

    def delete_key(self, key_id: str) -> bool:
        ok = youtube_key_db.delete_key(key_id)
        if ok:
            with self._lock:
                self._keys.pop(key_id, None)
        return ok

    # ── 每日重置 ────────────────────────────────────────────────────────

    def _maybe_reset_expired(self) -> None:
        """惰性触发每日配额重置：任何一次 pick_available 都会顺带检查。"""
        now = datetime.now(timezone.utc)
        need_reset: list[str] = []
        with self._lock:
            for key in self._keys.values():
                reset_at = _parse_iso(key.quota_reset_at)
                if not reset_at:
                    need_reset.append(key.key_id)
                    continue
                if now >= reset_at:
                    need_reset.append(key.key_id)

        if not need_reset:
            return

        new_reset = quota_tracker.compute_next_pt_midnight(now).isoformat()
        logger.info(
            "触发 YouTube Key 每日配额重置：共 %d 个 Key，重置点 %s",
            len(need_reset),
            new_reset,
        )
        youtube_key_db.bulk_reset_quota(new_reset_at=new_reset)

        with self._lock:
            for key_id in need_reset:
                key = self._keys.get(key_id)
                if not key:
                    continue
                key.quota_used_today = 0
                key.quota_reset_at = new_reset
                if key.status == "exhausted":
                    key.status = "active"

    # ── 汇总视图 ────────────────────────────────────────────────────────

    def summary(self) -> dict:
        self.ensure_loaded()
        self._maybe_reset_expired()
        with self._lock:
            total_limit = sum(k.daily_quota_limit for k in self._keys.values())
            total_used = sum(k.quota_used_today for k in self._keys.values())
            total_remaining = max(0, total_limit - total_used)
            active = sum(
                1 for k in self._keys.values() if k.enabled and k.status == "active"
            )
            exhausted = sum(1 for k in self._keys.values() if k.status == "exhausted")
            invalid = sum(1 for k in self._keys.values() if k.status == "invalid")
            earliest_reset = _earliest_reset(list(self._keys.values()))
            return {
                "total_keys": len(self._keys),
                "active_keys": active,
                "exhausted_keys": exhausted,
                "invalid_keys": invalid,
                "total_daily_limit": total_limit,
                "total_used_today": total_used,
                "total_remaining_today": total_remaining,
                "earliest_reset_at": earliest_reset,
                "keys": [k.to_public_dict() for k in self._keys.values()],
            }


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _earliest_reset(keys: Iterable[YouTubeApiKey]) -> Optional[str]:
    earliest: Optional[datetime] = None
    for key in keys:
        reset = _parse_iso(key.quota_reset_at)
        if not reset:
            continue
        if earliest is None or reset < earliest:
            earliest = reset
    return earliest.isoformat() if earliest else None


_POOL: Optional[YouTubeApiKeyPool] = None
_POOL_LOCK = threading.Lock()


def get_pool() -> YouTubeApiKeyPool:
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = YouTubeApiKeyPool()
    return _POOL
