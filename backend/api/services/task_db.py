"""
任务持久化层（SQLite）

职责：
- init_db()            : 建库建表
- save_task()          : 写入/更新任务摘要，并持久化完整结果到独立表
- save_task_summary()  : 仅更新高频摘要字段
- load_all_tasks()     : 启动时只加载摘要，避免将历史全量 tweets 读入内存
- load_task_result()   : 按需读取单任务完整结果
- delete_task()        : 删除任务与结果记录

设计原则：
- 内存层（_tasks dict）维持运行时高频读写，本模块只做 I/O 持久化
- 完整 tweets 结果从 tasks 主表拆出，避免轮询/启动路径反复处理大 JSON
- 对旧版数据库里的 tasks.tweets_json 做懒迁移兼容
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from json_utils import dump_json

logger = logging.getLogger(__name__)

_DB_PATH: Path | None = None
_local = threading.local()  # 线程本地存储，缓存连接


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（线程本地缓存，避免频繁创建）"""
    assert _DB_PATH is not None, "task_db 未初始化，请先调用 init_db()"
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # SQLite 性能优化配置
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-20000")  # 20MB
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB

        _local.conn = conn
    return conn


def init_db(db_path: str | Path) -> None:
    """
    初始化数据库：建库建表（如表不存在则创建）
    应在应用启动时调用一次。
    """
    global _DB_PATH
    new_path = Path(db_path)
    old_conn = getattr(_local, "conn", None)
    if old_conn is not None and _DB_PATH is not None and Path(_DB_PATH) != new_path:
        try:
            old_conn.close()
        except Exception:
            pass
        _local.conn = None

    _DB_PATH = new_path
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id               TEXT PRIMARY KEY,
                status                TEXT NOT NULL,
                keyword               TEXT NOT NULL,
                product               TEXT NOT NULL,
                max_count             INTEGER NOT NULL,
                result_count          INTEGER DEFAULT 0,
                current_page          INTEGER DEFAULT 0,
                created_at            TEXT NOT NULL,
                finished_at           TEXT,
                error                 TEXT,
                risk_state            TEXT DEFAULT 'none',
                quality_state         TEXT DEFAULT 'complete',
                runtime_metrics_json  TEXT DEFAULT '{}',
                time_coverage_json    TEXT DEFAULT '{}',
                last_event_at         TEXT,
                resumed               INTEGER DEFAULT 0,
                fetch_replies         INTEGER DEFAULT 0,
                max_replies_per_tweet INTEGER DEFAULT 0,
                reply_depth          INTEGER DEFAULT 2,
                crawl_strategy        TEXT DEFAULT 'dfs',
                replies_fetched       INTEGER DEFAULT 0,
                crawl_phase           TEXT DEFAULT '',
                task_kind             TEXT DEFAULT 'search',
                source_file_name      TEXT,
                source_task_id        TEXT,
                is_recrawl            INTEGER DEFAULT 0,
                exclude_count         INTEGER DEFAULT 0,
                queue_id              TEXT,
                queue_name            TEXT,
                queue_order           INTEGER,
                queue_total           INTEGER,
                comment_backfill_progress_json TEXT DEFAULT '{}',
                segment_progress_json TEXT DEFAULT '{}',
                tweets_json           TEXT DEFAULT '[]',
                preview_json          TEXT DEFAULT '[]'
                ,
                time_split_mode       TEXT DEFAULT 'inherit',
                time_split_window_days INTEGER,
                time_split_max_segments INTEGER
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_results (
                task_id      TEXT PRIMARY KEY,
                tweets_json  TEXT NOT NULL DEFAULT '[]',
                updated_at   TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_queues (
                queue_id      TEXT PRIMARY KEY,
                payload_json  TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            )
            """
        )

        # 失败评论记录表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS failed_replies (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id         TEXT NOT NULL,
                tweet_id        TEXT NOT NULL,
                screen_name     TEXT DEFAULT '',
                expected_count  INTEGER DEFAULT 0,
                fetched_count   INTEGER DEFAULT 0,
                error_reason    TEXT DEFAULT '',
                status          TEXT DEFAULT 'pending',
                created_at      TEXT NOT NULL,
                retried_at      TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_failed_replies_task
            ON failed_replies(task_id)
            """
        )

        # 添加关键索引以提升查询性能
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_queue_id ON tasks(queue_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_failed_replies_status ON failed_replies(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fingerprints_updated ON tweet_fingerprints(updated_at)"
        )

        # 用户设置持久化表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )

        # 推文指纹表（跨任务去重用）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tweet_fingerprints (
                tweet_id       TEXT PRIMARY KEY,
                fingerprint    TEXT NOT NULL,
                last_task_id   TEXT NOT NULL,
                replies_json   TEXT DEFAULT '[]',
                updated_at     TEXT NOT NULL
            )
            """
        )

        _ensure_column(conn, "tasks", "risk_state", "TEXT DEFAULT 'none'")
        _ensure_column(conn, "tasks", "quality_state", "TEXT DEFAULT 'complete'")
        _ensure_column(conn, "tasks", "runtime_metrics_json", "TEXT DEFAULT '{}'")
        _ensure_column(conn, "tasks", "time_coverage_json", "TEXT DEFAULT '{}'")
        _ensure_column(conn, "tasks", "last_event_at", "TEXT")
        _ensure_column(conn, "tasks", "platform", "TEXT DEFAULT 'x'")
        _ensure_column(conn, "tasks", "start_date", "TEXT")
        _ensure_column(conn, "tasks", "end_date", "TEXT")
        _ensure_column(conn, "tasks", "time_split_mode", "TEXT DEFAULT 'inherit'")
        _ensure_column(conn, "tasks", "time_split_window_days", "INTEGER")
        _ensure_column(conn, "tasks", "time_split_max_segments", "INTEGER")
        _ensure_column(conn, "tasks", "reply_depth", "INTEGER DEFAULT 2")
        _ensure_column(conn, "tasks", "segment_progress_json", "TEXT DEFAULT '{}'")
        _ensure_column(conn, "tasks", "task_kind", "TEXT DEFAULT 'search'")
        _ensure_column(conn, "tasks", "source_file_name", "TEXT")
        _ensure_column(conn, "tasks", "source_task_id", "TEXT")
        _ensure_column(conn, "tasks", "is_recrawl", "INTEGER DEFAULT 0")
        _ensure_column(conn, "tasks", "exclude_count", "INTEGER DEFAULT 0")
        _ensure_column(conn, "tasks", "queue_id", "TEXT")
        _ensure_column(conn, "tasks", "queue_name", "TEXT")
        _ensure_column(conn, "tasks", "queue_order", "INTEGER")
        _ensure_column(conn, "tasks", "queue_total", "INTEGER")
        _ensure_column(conn, "tasks", "comment_backfill_progress_json", "TEXT DEFAULT '{}'")
        _ensure_column(conn, "tasks", "source_task_ids_json", "TEXT DEFAULT '[]'")
        _ensure_column(conn, "tasks", "concurrency", "INTEGER DEFAULT 1")
        _ensure_column(conn, "tasks", "youtube_params_json", "TEXT")

        # 启动时清理超过 30 天的 tweet_fingerprints 记录，节省空间
        try:
            deleted_count = conn.execute(
                "DELETE FROM tweet_fingerprints WHERE updated_at < datetime('now','-30 days')"
            ).rowcount
            if deleted_count > 0:
                logger.info(f"已清理 {deleted_count} 条过期的 tweet_fingerprints 记录")
        except Exception as cleanup_err:
            logger.warning(f"清理过期 tweet_fingerprints 失败: {cleanup_err}")

        conn.commit()
    logger.info(f"任务数据库已初始化: {_DB_PATH}")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """对历史数据库做轻量补列，避免破坏已有数据。"""
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names = {c["name"] for c in cols}
    if column not in names:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _summary_params(task: dict) -> dict:
    youtube_params = task.get("youtube")
    youtube_json = (
        json.dumps(youtube_params, ensure_ascii=False)
        if isinstance(youtube_params, dict)
        else None
    )
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "keyword": task["keyword"],
        "product": task["product"],
        "max_count": int(task.get("max_count", 0) or 0),
        "result_count": task.get("result_count", 0),
        "current_page": task.get("current_page", 0),
        "created_at": task["created_at"],
        "finished_at": task.get("finished_at"),
        "error": task.get("error"),
        "risk_state": task.get("risk_state", "none"),
        "quality_state": task.get("quality_state", "complete"),
        "runtime_metrics_json": json.dumps(task.get("runtime_metrics", {}), ensure_ascii=False),
        "time_coverage_json": json.dumps(task.get("time_coverage", {}), ensure_ascii=False),
        "last_event_at": task.get("last_event_at"),
        "resumed": int(task.get("resumed", False)),
        "fetch_replies": int(task.get("fetch_replies", False)),
        "max_replies_per_tweet": task.get("max_replies_per_tweet", 0),
        "reply_depth": task.get("reply_depth", 2),
        "crawl_strategy": task.get("crawl_strategy", "dfs"),
        "replies_fetched": task.get("replies_fetched", 0),
        "crawl_phase": task.get("crawl_phase", ""),
        "task_kind": task.get("task_kind", "search"),
        "source_file_name": task.get("source_file_name"),
        "source_task_id": task.get("source_task_id"),
        "source_task_ids_json": json.dumps(task.get("source_task_ids") or [], ensure_ascii=False),
        "concurrency": int(task.get("concurrency") or 1),
        "is_recrawl": int(task.get("is_recrawl", False)),
        "exclude_count": task.get("exclude_count", 0),
        "queue_id": task.get("queue_id"),
        "queue_name": task.get("queue_name"),
        "queue_order": task.get("queue_order"),
        "queue_total": task.get("queue_total"),
        "comment_backfill_progress_json": json.dumps(
            task.get("comment_backfill_progress", {}),
            ensure_ascii=False,
        ),
        "segment_progress_json": json.dumps(task.get("segment_progress", {}), ensure_ascii=False),
        "preview_json": dump_json(task.get("preview_tweets", []), ensure_ascii=False),
        "platform": task.get("platform", "x"),
        "start_date": task.get("start_date"),
        "end_date": task.get("end_date"),
        "time_split_mode": task.get("time_split_mode", "inherit"),
        "time_split_window_days": task.get("time_split_window_days"),
        "time_split_max_segments": task.get("time_split_max_segments"),
        "youtube_params_json": youtube_json,
    }


def _upsert_task_summary(conn: sqlite3.Connection, task: dict) -> None:
    params = _summary_params(task)
    conn.execute(
        """
        INSERT INTO tasks (
            task_id, status, keyword, product, max_count,
            result_count, current_page, created_at, finished_at,
            error, risk_state, quality_state, runtime_metrics_json, time_coverage_json, last_event_at,
            resumed, fetch_replies, max_replies_per_tweet,
            reply_depth, crawl_strategy, replies_fetched, crawl_phase,
            task_kind, source_file_name, source_task_id, source_task_ids_json, concurrency, is_recrawl, exclude_count, queue_id, queue_name,
            queue_order, queue_total, comment_backfill_progress_json,
            segment_progress_json, preview_json,
            platform, start_date, end_date,
            time_split_mode, time_split_window_days, time_split_max_segments,
            youtube_params_json
        ) VALUES (
            :task_id, :status, :keyword, :product, :max_count,
            :result_count, :current_page, :created_at, :finished_at,
            :error, :risk_state, :quality_state, :runtime_metrics_json, :time_coverage_json, :last_event_at,
            :resumed, :fetch_replies, :max_replies_per_tweet,
            :reply_depth, :crawl_strategy, :replies_fetched, :crawl_phase,
            :task_kind, :source_file_name, :source_task_id, :source_task_ids_json, :concurrency, :is_recrawl, :exclude_count, :queue_id, :queue_name,
            :queue_order, :queue_total, :comment_backfill_progress_json,
            :segment_progress_json, :preview_json,
            :platform, :start_date, :end_date,
            :time_split_mode, :time_split_window_days, :time_split_max_segments,
            :youtube_params_json
        )
        ON CONFLICT(task_id) DO UPDATE SET
            status = excluded.status,
            keyword = excluded.keyword,
            product = excluded.product,
            max_count = excluded.max_count,
            result_count = excluded.result_count,
            current_page = excluded.current_page,
            created_at = excluded.created_at,
            finished_at = excluded.finished_at,
            error = excluded.error,
            risk_state = excluded.risk_state,
            quality_state = excluded.quality_state,
            runtime_metrics_json = excluded.runtime_metrics_json,
            time_coverage_json = excluded.time_coverage_json,
            last_event_at = excluded.last_event_at,
            resumed = excluded.resumed,
            fetch_replies = excluded.fetch_replies,
            max_replies_per_tweet = excluded.max_replies_per_tweet,
            reply_depth = excluded.reply_depth,
            crawl_strategy = excluded.crawl_strategy,
            replies_fetched = excluded.replies_fetched,
            crawl_phase = excluded.crawl_phase,
            task_kind = excluded.task_kind,
            source_file_name = excluded.source_file_name,
            source_task_id = excluded.source_task_id,
            source_task_ids_json = excluded.source_task_ids_json,
            concurrency = excluded.concurrency,
            is_recrawl = excluded.is_recrawl,
            exclude_count = excluded.exclude_count,
            queue_id = excluded.queue_id,
            queue_name = excluded.queue_name,
            queue_order = excluded.queue_order,
            queue_total = excluded.queue_total,
            comment_backfill_progress_json = excluded.comment_backfill_progress_json,
            segment_progress_json = excluded.segment_progress_json,
            preview_json = excluded.preview_json,
            platform = excluded.platform,
            start_date = excluded.start_date,
            end_date = excluded.end_date,
            time_split_mode = excluded.time_split_mode,
            time_split_window_days = excluded.time_split_window_days,
            time_split_max_segments = excluded.time_split_max_segments,
            youtube_params_json = excluded.youtube_params_json
        """,
        params,
    )


def save_task(task: dict) -> None:
    """
    写入或更新一条任务记录，并将完整 tweets 保存到独立结果表。
    """
    if _DB_PATH is None:
        return
    try:
        with _get_conn() as conn:
            _upsert_task_summary(conn, task)
            save_task_result(task["task_id"], task.get("tweets", []), conn=conn)
            conn.commit()
    except Exception as e:
        logger.error(f"持久化任务失败 task_id={task.get('task_id')}: {e}", exc_info=True)


def save_task_summary(task: dict) -> None:
    """
    仅更新高频摘要字段，不覆盖完整 tweets 结果。
    """
    if _DB_PATH is None:
        return
    try:
        with _get_conn() as conn:
            _upsert_task_summary(conn, task)
            conn.commit()
    except Exception as e:
        logger.error(f"摘要持久化失败 task_id={task.get('task_id')}: {e}", exc_info=True)


def save_task_result(
    task_id: str,
    tweets: list[dict],
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """写入任务完整结果。"""
    if _DB_PATH is None:
        return

    owns_conn = conn is None
    conn = conn or _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO task_results (task_id, tweets_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                tweets_json = excluded.tweets_json,
                updated_at = excluded.updated_at
            """,
            (task_id, dump_json(tweets, ensure_ascii=False), _now_iso()),
        )
        if owns_conn:
            conn.commit()
    except Exception:
        if owns_conn:
            conn.rollback()
        raise


def _decode_result_json(raw: object) -> list[dict]:
    try:
        decoded = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


def load_task_result(task_id: str) -> list[dict]:
    """
    按需加载任务完整结果。

    优先从 task_results 读取；若不存在，则回退到旧版 tasks.tweets_json，
    并在成功读取后懒迁移到新表。
    """
    if _DB_PATH is None or not _DB_PATH.exists():
        return []
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT tweets_json FROM task_results WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row:
                return _decode_result_json(row["tweets_json"])

            legacy = conn.execute(
                "SELECT tweets_json FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if not legacy:
                return []

            tweets = _decode_result_json(legacy["tweets_json"])
            if tweets:
                save_task_result(task_id, tweets, conn=conn)
                conn.commit()
            return tweets
    except Exception as e:
        logger.error(f"读取任务结果失败 task_id={task_id}: {e}", exc_info=True)
        return []


def load_cached_replies_map(tweet_ids: list[str]) -> dict[str, list[dict]]:
    """按 tweet_id 批量读取评论缓存。"""
    if _DB_PATH is None or not _DB_PATH.exists():
        return {}

    normalized_ids = [str(tweet_id or "").strip() for tweet_id in tweet_ids if str(tweet_id or "").strip()]
    if not normalized_ids:
        return {}

    result: dict[str, list[dict]] = {}
    try:
        with _get_conn() as conn:
            chunk_size = 500
            for start in range(0, len(normalized_ids), chunk_size):
                chunk = normalized_ids[start:start + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"""
                    SELECT tweet_id, replies_json
                    FROM tweet_fingerprints
                    WHERE tweet_id IN ({placeholders})
                    """,
                    chunk,
                ).fetchall()
                for row in rows:
                    result[str(row["tweet_id"])] = _decode_result_json(row["replies_json"])
        return result
    except Exception as e:
        logger.error(f"读取评论缓存失败: {e}", exc_info=True)
        return {}


def load_all_tasks() -> list[dict]:
    """
    从数据库加载全部历史任务摘要（服务启动时调用一次）。
    不加载全量 tweets，避免启动时间和内存占用随历史数据放大。
    """
    if _DB_PATH is None or not _DB_PATH.exists():
        return []
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    task_id, status, keyword, product, max_count,
                    result_count, current_page, created_at, finished_at,
                    error, risk_state, quality_state, runtime_metrics_json, time_coverage_json,
                    last_event_at, resumed, fetch_replies, max_replies_per_tweet,
                    reply_depth, crawl_strategy, replies_fetched, crawl_phase,
                    task_kind, source_file_name, source_task_id, source_task_ids_json, concurrency, is_recrawl, exclude_count, queue_id, queue_name,
                    queue_order, queue_total, comment_backfill_progress_json, segment_progress_json,
                    preview_json, platform, start_date, end_date,
                    time_split_mode, time_split_window_days, time_split_max_segments,
                    youtube_params_json
                FROM tasks
                ORDER BY created_at DESC
                """
            ).fetchall()

        tasks = []
        for row in rows:
            d = dict(row)
            d["tweets"] = []
            d["preview_tweets"] = _decode_result_json(d.pop("preview_json", "[]"))
            d["risk_state"] = d.get("risk_state") or "none"
            d["quality_state"] = d.get("quality_state") or "complete"
            d["runtime_metrics"] = json.loads(d.pop("runtime_metrics_json", "{}") or "{}")
            d["time_coverage"] = json.loads(d.pop("time_coverage_json", "{}") or "{}")
            d["comment_backfill_progress"] = json.loads(
                d.pop("comment_backfill_progress_json", "{}") or "{}"
            )
            d["segment_progress"] = json.loads(d.pop("segment_progress_json", "{}") or "{}")
            d["source_task_ids"] = json.loads(d.pop("source_task_ids_json", "[]") or "[]")
            d["resumed"] = bool(d["resumed"])
            d["fetch_replies"] = bool(d["fetch_replies"])
            d.setdefault("task_kind", "search")
            d.setdefault("source_file_name", None)
            d.setdefault("source_task_id", None)
            d["is_recrawl"] = bool(d.get("is_recrawl", 0))
            d["exclude_count"] = int(d.get("exclude_count", 0) or 0)
            d.setdefault("queue_id", None)
            d.setdefault("queue_name", None)
            d.setdefault("queue_order", None)
            d.setdefault("queue_total", None)
            d.setdefault("platform", "x")
            d.setdefault("time_split_mode", "inherit")
            d.setdefault("time_split_window_days", None)
            d.setdefault("time_split_max_segments", None)
            youtube_raw = d.pop("youtube_params_json", None)
            if youtube_raw:
                try:
                    d["youtube"] = json.loads(youtube_raw)
                except (TypeError, json.JSONDecodeError):
                    d["youtube"] = None
            else:
                d["youtube"] = None
            tasks.append(d)
        logger.info(f"已从数据库加载 {len(tasks)} 条历史任务摘要")
        return tasks
    except Exception as e:
        logger.error(f"加载历史任务失败: {e}", exc_info=True)
        return []


def delete_task(task_id: str) -> None:
    """从数据库删除任务记录与完整结果。"""
    if _DB_PATH is None:
        return
    try:
        with _get_conn() as conn:
            conn.execute("DELETE FROM task_results WHERE task_id = ?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            conn.commit()

            # 定期触发 VACUUM 以回收已删除数据的磁盘空间
            # 使用概率触发，避免每次删除都执行昂贵的 VACUUM 操作
            import random
            if random.random() < 0.05:  # 5% 概率
                try:
                    conn.execute("PRAGMA incremental_vacuum(100)")  # 释放最多 100 页
                except Exception as vacuum_err:
                    logger.debug(f"增量 VACUUM 执行失败: {vacuum_err}")
    except Exception as e:
        logger.error(f"删除任务记录失败 task_id={task_id}: {e}", exc_info=True)


def save_task_queue(queue_data: dict) -> None:
    if _DB_PATH is None:
        return
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO task_queues (queue_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(queue_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    queue_data["queue_id"],
                    json.dumps(queue_data, ensure_ascii=False),
                    _now_iso(),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"持久化任务队列失败 queue_id={queue_data.get('queue_id')}: {e}", exc_info=True)


def load_task_queues() -> list[dict]:
    if _DB_PATH is None or not _DB_PATH.exists():
        return []
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM task_queues ORDER BY updated_at DESC"
            ).fetchall()
        queues: list[dict] = []
        for row in rows:
            try:
                decoded = json.loads(row["payload_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(decoded, dict) and decoded.get("queue_id"):
                queues.append(decoded)
        return queues
    except Exception as e:
        logger.error(f"读取任务队列失败: {e}", exc_info=True)
        return []
