"""
YouTube API Key 持久化层（SQLite）

表结构 youtube_api_keys：
- key_id             UUID 主键
- alias              用户备注（显示名）
- api_key            实际 API Key 明文
- enabled            是否启用
- daily_quota_limit  每日配额上限（默认 10000）
- quota_used_today   今日已用配额
- quota_reset_at     配额重置时间（ISO，PT 00:00 UTC-8 换算为 UTC）
- status             active / exhausted / invalid
- last_used_at       最近使用时间
- last_validated_at  最近验证成功时间
- fail_count         连续失败次数
- last_error         最近一次失败原因
- created_at         创建时间
- updated_at         最后更新时间

Key 池运行时以内存为主，持久化层仅负责启动加载 + 写回变更。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_TABLE_NAME = "youtube_api_keys"


def _get_conn() -> sqlite3.Connection:
    """复用 task_db 的数据库连接（线程本地缓存）。"""
    from api.services.task_db import _get_conn as _db_conn

    return _db_conn()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_schema() -> None:
    """首次调用时建表；已存在则跳过。"""
    try:
        with _get_conn() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
                    key_id             TEXT PRIMARY KEY,
                    alias              TEXT NOT NULL,
                    api_key            TEXT NOT NULL,
                    enabled            INTEGER DEFAULT 1,
                    daily_quota_limit  INTEGER DEFAULT 10000,
                    quota_used_today   INTEGER DEFAULT 0,
                    quota_reset_at     TEXT,
                    status             TEXT DEFAULT 'active',
                    last_used_at       TEXT,
                    last_validated_at  TEXT,
                    fail_count         INTEGER DEFAULT 0,
                    last_error         TEXT,
                    created_at         TEXT NOT NULL,
                    updated_at         TEXT NOT NULL
                )
                """
            )
            conn.commit()
    except Exception as e:
        logger.error(f"youtube_api_keys 建表失败: {e}", exc_info=True)


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["enabled"] = bool(data.get("enabled", 0))
    data["daily_quota_limit"] = int(data.get("daily_quota_limit") or 10000)
    data["quota_used_today"] = int(data.get("quota_used_today") or 0)
    data["fail_count"] = int(data.get("fail_count") or 0)
    data["status"] = data.get("status") or "active"
    return data


def list_all_keys() -> list[dict]:
    ensure_schema()
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {_TABLE_NAME} ORDER BY created_at ASC"
            ).fetchall()
        return [_row_to_dict(row) for row in rows]
    except Exception as e:
        logger.error(f"加载 YouTube Key 列表失败: {e}", exc_info=True)
        return []


def get_key(key_id: str) -> Optional[dict]:
    ensure_schema()
    try:
        with _get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {_TABLE_NAME} WHERE key_id = ?",
                (key_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None
    except Exception as e:
        logger.error(f"读取 YouTube Key 失败 key_id={key_id}: {e}", exc_info=True)
        return None


def insert_key(
    *,
    alias: str,
    api_key: str,
    daily_quota_limit: int = 10000,
    enabled: bool = True,
    quota_reset_at: Optional[str] = None,
) -> dict:
    ensure_schema()
    key_id = str(uuid.uuid4())
    now = _now_iso()
    payload = {
        "key_id": key_id,
        "alias": alias.strip() or f"Key-{key_id[:6]}",
        "api_key": api_key.strip(),
        "enabled": 1 if enabled else 0,
        "daily_quota_limit": int(daily_quota_limit),
        "quota_used_today": 0,
        "quota_reset_at": quota_reset_at,
        "status": "active",
        "last_used_at": None,
        "last_validated_at": None,
        "fail_count": 0,
        "last_error": None,
        "created_at": now,
        "updated_at": now,
    }
    with _get_conn() as conn:
        conn.execute(
            f"""
            INSERT INTO {_TABLE_NAME} (
                key_id, alias, api_key, enabled, daily_quota_limit, quota_used_today,
                quota_reset_at, status, last_used_at, last_validated_at, fail_count,
                last_error, created_at, updated_at
            ) VALUES (
                :key_id, :alias, :api_key, :enabled, :daily_quota_limit, :quota_used_today,
                :quota_reset_at, :status, :last_used_at, :last_validated_at, :fail_count,
                :last_error, :created_at, :updated_at
            )
            """,
            payload,
        )
        conn.commit()
    return get_key(key_id) or payload


def update_key(key_id: str, fields: dict) -> Optional[dict]:
    """按字段白名单更新。"""
    if not fields:
        return get_key(key_id)

    allowed = {
        "alias",
        "api_key",
        "enabled",
        "daily_quota_limit",
        "quota_used_today",
        "quota_reset_at",
        "status",
        "last_used_at",
        "last_validated_at",
        "fail_count",
        "last_error",
    }
    normalized: dict = {}
    for field_name, value in fields.items():
        if field_name not in allowed:
            continue
        if field_name == "enabled":
            normalized[field_name] = 1 if value else 0
        else:
            normalized[field_name] = value
    if not normalized:
        return get_key(key_id)

    normalized["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = :{k}" for k in normalized)
    normalized["key_id"] = key_id
    with _get_conn() as conn:
        conn.execute(
            f"UPDATE {_TABLE_NAME} SET {set_clause} WHERE key_id = :key_id",
            normalized,
        )
        conn.commit()
    return get_key(key_id)


def delete_key(key_id: str) -> bool:
    ensure_schema()
    try:
        with _get_conn() as conn:
            cursor = conn.execute(
                f"DELETE FROM {_TABLE_NAME} WHERE key_id = ?",
                (key_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"删除 YouTube Key 失败 key_id={key_id}: {e}", exc_info=True)
        return False


def bulk_reset_quota(*, new_reset_at: str) -> int:
    """每日重置：清零 quota_used_today，状态 exhausted → active。"""
    ensure_schema()
    try:
        with _get_conn() as conn:
            cursor = conn.execute(
                f"""
                UPDATE {_TABLE_NAME}
                SET quota_used_today = 0,
                    quota_reset_at   = :reset_at,
                    status           = CASE WHEN status = 'exhausted' THEN 'active' ELSE status END,
                    updated_at       = :now
                """,
                {"reset_at": new_reset_at, "now": _now_iso()},
            )
            conn.commit()
            return cursor.rowcount or 0
    except Exception as e:
        logger.error(f"批量重置 YouTube Key 配额失败: {e}", exc_info=True)
        return 0
