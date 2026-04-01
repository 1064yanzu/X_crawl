"""
采集量分桶持久化模块（10 分钟粒度）

每当 telemetry 记录到新推文/评论时，同步写入一条 10 分钟分桶记录。
提供给 analytics 路由查询「每 10 分钟采集了多少数据」的视图。

表设计（crawl_volume_buckets）：
  bucket_key  TEXT  PRIMARY KEY  -- 格式: "YYYY-MM-DDTHH:MM"（每 10 分钟一格）
  tweets      INTEGER DEFAULT 0  -- 该桶累计推文数
  replies     INTEGER DEFAULT 0  -- 该桶累计评论数
  updated_at  TEXT               -- 最后更新时间
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH: Optional[Path] = None
_local = threading.local()
_write_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    assert _DB_PATH is not None, "crawl_volume_db 未初始化，请先调用 init_volume_db()"
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def init_volume_db(db_path: str | Path) -> None:
    """初始化采集量分桶数据库（与主任务库共用同一 SQLite 文件）。"""
    global _DB_PATH
    _DB_PATH = Path(db_path)
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_volume_buckets (
                    bucket_key  TEXT PRIMARY KEY,
                    tweets      INTEGER DEFAULT 0,
                    replies     INTEGER DEFAULT 0,
                    updated_at  TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cvb_bucket_key
                ON crawl_volume_buckets(bucket_key)
                """
            )
            conn.commit()
        logger.info("采集量分桶数据库已初始化")
    except Exception as e:
        logger.error(f"初始化采集量分桶数据库失败: {e}", exc_info=True)


def _bucket_key(dt: Optional[datetime] = None) -> str:
    """将时间截断到 10 分钟粒度，返回 bucket key：'YYYY-MM-DDTHH:M0'"""
    if dt is None:
        dt = datetime.now(timezone.utc)
    # 截断到 10 分钟
    minute = (dt.minute // 10) * 10
    return dt.strftime(f"%Y-%m-%dT%H:{minute:02d}")


def write_volume(
    delta_tweets: int = 0,
    delta_replies: int = 0,
    *,
    at: Optional[datetime] = None,
) -> None:
    """
    写入一条采集量增量到当前 10 分钟分桶。
    线程安全，使用 UPSERT 累加。
    """
    if _DB_PATH is None:
        return
    if delta_tweets <= 0 and delta_replies <= 0:
        return

    key = _bucket_key(at)
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        with _write_lock:
            with _get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO crawl_volume_buckets (bucket_key, tweets, replies, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(bucket_key) DO UPDATE SET
                        tweets     = tweets + excluded.tweets,
                        replies    = replies + excluded.replies,
                        updated_at = excluded.updated_at
                    """,
                    (key, max(0, delta_tweets), max(0, delta_replies), now_iso),
                )
                conn.commit()
    except Exception as e:
        logger.debug(f"写入采集量分桶失败（忽略）: {e}")


def query_volume(
    *,
    since: Optional[str] = None,
    limit: int = 288,   # 默认 288 个 10 分钟桶 = 48 小时
) -> list[dict]:
    """
    查询采集量分桶数据，按 bucket_key 升序排列。

    Args:
        since: ISO 格式时间字符串，只返回该时间之后的桶（如 '2026-03-25T00:00'）
        limit: 最多返回多少个桶

    Returns:
        [{"bucket": "2026-03-25T14:10", "tweets": 120, "replies": 45}, ...]
    """
    if _DB_PATH is None or not _DB_PATH.exists():
        return []
    try:
        with _get_conn() as conn:
            if since:
                rows = conn.execute(
                    """
                    SELECT bucket_key, tweets, replies
                    FROM crawl_volume_buckets
                    WHERE bucket_key >= ?
                    ORDER BY bucket_key ASC
                    LIMIT ?
                    """,
                    (since, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT bucket_key, tweets, replies
                    FROM crawl_volume_buckets
                    ORDER BY bucket_key DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                rows = list(reversed(rows))

        return [
            {
                "bucket": row["bucket_key"],
                "tweets": int(row["tweets"]),
                "replies": int(row["replies"]),
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"查询采集量分桶失败: {e}", exc_info=True)
        return []
