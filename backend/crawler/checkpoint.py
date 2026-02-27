"""
断点续爬检查点模块
将每次任务的爬取进度（已爬推文 + cursor）持久化到 JSON 文件
服务重启后可从断点处继续爬取，不重新开始
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 检查点保存目录
_CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoints"


def _get_checkpoint_path(task_id: str) -> Path:
    """返回指定任务的检查点文件路径"""
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return _CHECKPOINT_DIR / f"{task_id}.json"


def save_checkpoint(
    task_id: str,
    keyword: str,
    product: str,
    tweets_so_far: list[dict],
    next_cursor: Optional[str],
    page_fetched: int,
) -> None:
    """
    保存断点到磁盘

    Args:
        task_id:       任务 ID
        keyword:       搜索关键词
        product:       搜索类型
        tweets_so_far: 已爬取的推文列表
        next_cursor:   下一页 cursor（None 表示已爬完）
        page_fetched:  已爬取页数
    """
    path = _get_checkpoint_path(task_id)
    data = {
        "task_id": task_id,
        "keyword": keyword,
        "product": product,
        "tweets": tweets_so_far,
        "next_cursor": next_cursor,
        "page_fetched": page_fetched,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        tmp_path.replace(path)
        logger.debug(f"检查点已保存: {path}（{len(tweets_so_far)} 条推文，cursor={'有' if next_cursor else '无'}）")
    except Exception as e:
        logger.error(f"保存检查点失败: {e}")


def load_checkpoint(task_id: str) -> Optional[dict]:
    """
    加载任务检查点

    Returns:
        检查点数据 dict，不存在则返回 None
    """
    path = _get_checkpoint_path(task_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(
            f"加载检查点: task_id={task_id}，"
            f"已有 {len(data.get('tweets', []))} 条推文，"
            f"cursor={'有' if data.get('next_cursor') else '无'}，"
            f"已爬 {data.get('page_fetched', 0)} 页"
        )
        return data
    except Exception as e:
        logger.error(f"加载检查点失败: {e}")
        return None


def delete_checkpoint(task_id: str) -> None:
    """任务完成后删除检查点文件"""
    path = _get_checkpoint_path(task_id)
    try:
        if path.exists():
            path.unlink()
            logger.debug(f"检查点已删除: {path}")
    except Exception as e:
        logger.warning(f"删除检查点失败: {e}")


def list_checkpoints() -> list[dict]:
    """
    列出所有未完成的检查点
    用于 API 展示可恢复的任务
    """
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for p in _CHECKPOINT_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            result.append({
                "task_id": data.get("task_id"),
                "keyword": data.get("keyword"),
                "product": data.get("product"),
                "tweets_count": len(data.get("tweets", [])),
                "page_fetched": data.get("page_fetched", 0),
                "saved_at": data.get("saved_at"),
                "can_resume": bool(data.get("next_cursor")),
            })
        except Exception:
            pass
    result.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return result
