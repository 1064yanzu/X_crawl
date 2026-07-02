"""
失败评论记录数据访问层

职责：
- record_failed_reply()       : 记录一条失败/不全的评论抓取
- list_failed_replies()       : 查询指定任务的失败记录
- update_failed_reply_status(): 重试后更新状态
- delete_failed_replies()     : 清除任务的失败记录
- count_failed_replies()      : 统计任务失败记录数
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_conn():
    """复用 task_db 的数据库连接"""
    from api.services.task_db import _get_conn as _db_conn
    return _db_conn()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_failed_reply(
    task_id: str,
    tweet_id: str,
    screen_name: str,
    expected_count: int,
    fetched_count: int,
    error_reason: str,
) -> None:
    """记录一条失败/不全的评论抓取"""
    try:
        with _get_conn() as conn:
            # 如果已有同一 task_id + tweet_id 的记录，更新它
            existing = conn.execute(
                "SELECT id FROM failed_replies WHERE task_id = ? AND tweet_id = ?",
                (task_id, tweet_id),
            ).fetchone()
            if existing:
                conn.execute("""
                    UPDATE failed_replies SET
                        expected_count = ?,
                        fetched_count = ?,
                        error_reason = ?,
                        status = 'pending',
                        created_at = ?
                    WHERE task_id = ? AND tweet_id = ?
                """, (expected_count, fetched_count, error_reason, _now_iso(), task_id, tweet_id))
            else:
                conn.execute("""
                    INSERT INTO failed_replies
                        (task_id, tweet_id, screen_name, expected_count, fetched_count, error_reason, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """, (task_id, tweet_id, screen_name, expected_count, fetched_count, error_reason, _now_iso()))
            conn.commit()
    except Exception as e:
        logger.error(f"记录失败评论失败: task_id={task_id}, tweet_id={tweet_id}: {e}", exc_info=True)


def record_failed_replies_batch(records: list[dict]) -> None:
    """批量记录失败评论（单次 commit + executemany，避免逐条事务开销）。"""
    if not records:
        return
    now = _now_iso()
    rows = [
        (
            rec["task_id"],
            rec["tweet_id"],
            rec.get("screen_name", ""),
            int(rec.get("expected_count", 0) or 0),
            int(rec.get("fetched_count", 0) or 0),
            rec.get("error_reason", ""),
            now,
        )
        for rec in records
        if rec.get("task_id") and rec.get("tweet_id")
    ]
    if not rows:
        return
    try:
        with _get_conn() as conn:
            conn.executemany(
                """
                INSERT INTO failed_replies
                    (task_id, tweet_id, screen_name, expected_count, fetched_count,
                     error_reason, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                rows,
            )
            conn.commit()
    except Exception as e:
        logger.error(f"批量记录失败评论失败（rows={len(rows)}）: {e}", exc_info=True)


def list_failed_replies(task_id: str) -> list[dict]:
    """查询指定任务的所有失败记录"""
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM failed_replies WHERE task_id = ? ORDER BY created_at DESC",
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"查询失败记录失败: task_id={task_id}: {e}", exc_info=True)
        return []


def update_failed_reply_status(
    task_id: str,
    tweet_id: str,
    status: str,
    fetched_count: int | None = None,
) -> None:
    """更新失败记录的状态（pending → retrying → resolved）"""
    try:
        with _get_conn() as conn:
            if fetched_count is not None:
                conn.execute("""
                    UPDATE failed_replies SET status = ?, fetched_count = ?, retried_at = ?
                    WHERE task_id = ? AND tweet_id = ?
                """, (status, fetched_count, _now_iso(), task_id, tweet_id))
            else:
                conn.execute("""
                    UPDATE failed_replies SET status = ?, retried_at = ?
                    WHERE task_id = ? AND tweet_id = ?
                """, (status, _now_iso(), task_id, tweet_id))
            conn.commit()
    except Exception as e:
        logger.error(f"更新失败记录状态失败: task_id={task_id}, tweet_id={tweet_id}: {e}", exc_info=True)


def count_failed_replies(task_id: str) -> dict:
    """统计失败记录数（按状态分组）"""
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM failed_replies WHERE task_id = ? GROUP BY status",
                (task_id,),
            ).fetchall()
        result = {"total": 0, "pending": 0, "retrying": 0, "resolved": 0}
        for row in rows:
            result[row["status"]] = row["cnt"]
            result["total"] += row["cnt"]
        return result
    except Exception as e:
        logger.error(f"统计失败记录失败: task_id={task_id}: {e}", exc_info=True)
        return {"total": 0, "pending": 0, "retrying": 0, "resolved": 0}


def delete_failed_replies(task_id: str) -> int:
    """清除任务的所有失败记录，返回删除行数"""
    try:
        with _get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM failed_replies WHERE task_id = ?", (task_id,)
            )
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        logger.error(f"删除失败记录失败: task_id={task_id}: {e}", exc_info=True)
        return 0
