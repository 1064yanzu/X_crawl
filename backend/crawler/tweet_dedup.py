"""
跨任务推文去重模块（缓存命中）

当不同关键词搜索结果命中相同推文时，通过指纹比对避免重复抓取评论。
指纹算法基于推文 ID + 互动指标（评论数、转发数、点赞数），
指标未变化则认为评论内容也未变化，直接复用上次抓到的评论数据。

使用方式：
  from crawler.tweet_dedup import check_dedup, register_tweets

  # 检查某条推文是否命中缓存
  hit, cached_replies = check_dedup(tweet)
  if hit:
      tweet["replies"] = cached_replies  # 跳过评论抓取

  # 抓取完成后注册指纹
  register_tweets(tweets_with_replies, task_id)
"""
import hashlib
import json
import logging
import sqlite3
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# 惰性连接，复用 task_db 的数据库路径
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（复用 task_db 的路径）"""
    conn = getattr(_local, "dedup_conn", None)
    if conn is None:
        from api.services.task_db import _DB_PATH
        if _DB_PATH is None:
            raise RuntimeError("task_db 未初始化")
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.dedup_conn = conn
    return conn


def compute_fingerprint(tweet: dict) -> str:
    """
    计算推文互动指标指纹。

    指纹仅基于可变的互动数据（评论数/转发数/点赞数），
    推文文本和发布时间是不变量，不纳入指纹。
    """
    metrics = tweet.get("metrics") or {}
    data = {
        "replies": metrics.get("replies", 0),
        "retweets": metrics.get("retweets", 0),
        "likes": metrics.get("likes", 0),
    }
    raw = json.dumps(data, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def check_dedup(tweet: dict) -> tuple[bool, list[dict] | None]:
    """
    检查推文是否可以跳过评论抓取（缓存命中）。

    Returns:
        (hit, cached_replies)
        - hit=True, cached_replies=[...]: 指纹匹配，可复用历史评论
        - hit=False, None:               需要重新抓取评论
    """
    tweet_id = tweet.get("id", "")
    if not tweet_id:
        return False, None

    try:
        fp = compute_fingerprint(tweet)
        conn = _get_conn()
        row = conn.execute(
            "SELECT fingerprint, replies_json FROM tweet_fingerprints WHERE tweet_id = ?",
            (tweet_id,)
        ).fetchone()

        if row is None:
            return False, None

        if row["fingerprint"] == fp:
            try:
                cached = json.loads(row["replies_json"] or "[]")
                logger.debug(f"去重命中: tweet_id={tweet_id}, 复用 {len(cached)} 条缓存评论")
                return True, cached
            except (json.JSONDecodeError, TypeError):
                return False, None

        # 指纹不同 → 推文有更新
        logger.debug(f"去重未命中（指纹变化）: tweet_id={tweet_id}")
        return False, None

    except Exception as e:
        logger.debug(f"去重检查异常（不影响主流程）: {e}")
        return False, None


def register_tweets(
    tweets: list[dict],
    task_id: str,
) -> int:
    """
    批量注册推文指纹和评论缓存。

    在评论抓取完成后调用，将推文的指纹 + 评论数据写入数据库。

    Returns:
        成功注册的数量
    """
    if not tweets:
        return 0

    try:
        conn = _get_conn()
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        count = 0

        for tweet in tweets:
            tweet_id = tweet.get("id", "")
            if not tweet_id:
                continue

            replies = tweet.get("replies")
            # 只注册有评论数据的推文（包括空列表，表示确认过无评论）
            if replies is None:
                continue

            fp = compute_fingerprint(tweet)
            replies_json = json.dumps(replies, ensure_ascii=False)

            conn.execute("""
                INSERT OR REPLACE INTO tweet_fingerprints
                    (tweet_id, fingerprint, last_task_id, replies_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (tweet_id, fp, task_id, replies_json, now))
            count += 1

        conn.commit()
        if count:
            logger.info(f"去重缓存已注册 {count} 条推文指纹 (task_id={task_id})")
        return count

    except Exception as e:
        logger.error(f"注册推文指纹异常: {e}", exc_info=True)
        return 0
