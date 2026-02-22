"""
任务持久化层（SQLite）

职责：
- init_db()       : 建库建表
- save_task()     : 写入/更新任务（INSERT OR REPLACE）
- load_all_tasks(): 启动时加载全部历史任务到内存
- delete_task()   : 删除任务

设计原则：
- 内存层（_tasks dict）维持运行时高频读写，本模块只做 I/O 持久化
- 推文数据以 JSON 字符串存储在 tweets_json / preview_json 列
- update_task_phase 极频繁（每页多次），不持久化，避免写入风暴
"""
import json
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH: Path | None = None


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（每次调用返回新连接，线程安全）"""
    assert _DB_PATH is not None, "task_db 未初始化，请先调用 init_db()"
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path) -> None:
    """
    初始化数据库：建库建表（如表不存在则创建）
    应在应用启动时调用一次。
    """
    global _DB_PATH
    _DB_PATH = Path(db_path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _get_conn() as conn:
        conn.execute("""
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
                resumed               INTEGER DEFAULT 0,
                fetch_replies         INTEGER DEFAULT 0,
                max_replies_per_tweet INTEGER DEFAULT 0,
                crawl_strategy        TEXT DEFAULT 'dfs',
                replies_fetched       INTEGER DEFAULT 0,
                crawl_phase           TEXT DEFAULT '',
                tweets_json           TEXT DEFAULT '[]',
                preview_json          TEXT DEFAULT '[]'
            )
        """)
        conn.commit()
    logger.info(f"任务数据库已初始化: {_DB_PATH}")


def save_task(task: dict) -> None:
    """
    写入或更新一条任务记录（INSERT OR REPLACE）。
    传入 task_manager 中的完整 task dict。
    """
    if _DB_PATH is None:
        return
    try:
        tweets_json = json.dumps(task.get("tweets", []), ensure_ascii=False)
        preview_json = json.dumps(task.get("preview_tweets", []), ensure_ascii=False)
        with _get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tasks (
                    task_id, status, keyword, product, max_count,
                    result_count, current_page, created_at, finished_at,
                    error, resumed, fetch_replies, max_replies_per_tweet,
                    crawl_strategy, replies_fetched, crawl_phase,
                    tweets_json, preview_json
                ) VALUES (
                    :task_id, :status, :keyword, :product, :max_count,
                    :result_count, :current_page, :created_at, :finished_at,
                    :error, :resumed, :fetch_replies, :max_replies_per_tweet,
                    :crawl_strategy, :replies_fetched, :crawl_phase,
                    :tweets_json, :preview_json
                )
            """, {
                "task_id":               task["task_id"],
                "status":                task["status"],
                "keyword":               task["keyword"],
                "product":               task["product"],
                "max_count":             task["max_count"],
                "result_count":          task.get("result_count", 0),
                "current_page":          task.get("current_page", 0),
                "created_at":            task["created_at"],
                "finished_at":           task.get("finished_at"),
                "error":                 task.get("error"),
                "resumed":               int(task.get("resumed", False)),
                "fetch_replies":         int(task.get("fetch_replies", False)),
                "max_replies_per_tweet": task.get("max_replies_per_tweet", 0),
                "crawl_strategy":        task.get("crawl_strategy", "dfs"),
                "replies_fetched":       task.get("replies_fetched", 0),
                "crawl_phase":           task.get("crawl_phase", ""),
                "tweets_json":           tweets_json,
                "preview_json":          preview_json,
            })
            conn.commit()
    except Exception as e:
        logger.error(f"持久化任务失败 task_id={task.get('task_id')}: {e}", exc_info=True)


def load_all_tasks() -> list[dict]:
    """
    从数据库加载全部历史任务（服务启动时调用一次）。
    返回 task_manager 格式的 dict 列表。
    """
    if _DB_PATH is None or not _DB_PATH.exists():
        return []
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC"
            ).fetchall()
        tasks = []
        for row in rows:
            d = dict(row)
            d["tweets"]        = json.loads(d.pop("tweets_json", "[]") or "[]")
            d["preview_tweets"] = json.loads(d.pop("preview_json", "[]") or "[]")
            d["resumed"]        = bool(d["resumed"])
            d["fetch_replies"]  = bool(d["fetch_replies"])
            tasks.append(d)
        logger.info(f"已从数据库加载 {len(tasks)} 条历史任务")
        return tasks
    except Exception as e:
        logger.error(f"加载历史任务失败: {e}", exc_info=True)
        return []


def delete_task(task_id: str) -> None:
    """从数据库删除任务记录"""
    if _DB_PATH is None:
        return
    try:
        with _get_conn() as conn:
            conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"删除任务记录失败 task_id={task_id}: {e}", exc_info=True)
