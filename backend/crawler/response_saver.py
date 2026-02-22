"""
原始响应持久化模块

将每次爬取到的 SearchTimeline 原始 JSON 响应保存到本地磁盘，
用于数据安全备份与离线回溯分析。

存储结构：
    {raw_responses_dir}/{task_id}/page_{n}_{timestamp}.json
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def _get_task_dir(task_id: str) -> Path:
    """获取指定任务的原始响应存储目录（自动创建）"""
    base = Path(settings.raw_responses_dir)
    task_dir = base / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def save_raw_response(task_id: str, page_num: int, body: dict) -> Optional[str]:
    """
    保存原始响应 JSON 到磁盘。

    Args:
        task_id:  当前任务 ID，用于子目录命名
        page_num: 当前页码（从 1 开始）
        body:     原始响应 dict（即监听到的 packet.response.body）

    Returns:
        保存的文件绝对路径，若未开启保存则返回 None
    """
    if not settings.save_raw_responses:
        return None

    # 每任务最大保存页数检查
    max_pages = settings.raw_responses_max_pages
    if max_pages and page_num > max_pages:
        logger.debug(
            f"已达最大保存页数 {max_pages}，跳过第 {page_num} 页原始响应"
        )
        return None

    try:
        task_dir = _get_task_dir(task_id)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"page_{page_num:03d}_{ts}.json"
        file_path = task_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)

        size_kb = file_path.stat().st_size / 1024
        logger.info(
            f"原始响应已保存: {file_path.name} ({size_kb:.1f} KB)"
        )
        return str(file_path)
    except Exception as e:
        # 保存失败不影响主流程
        logger.warning(f"保存原始响应失败（task_id={task_id}, page={page_num}）: {e}")
        return None


def get_task_response_dir(task_id: str) -> Path:
    """返回指定任务原始响应目录的 Path 对象（不自动创建）"""
    return Path(settings.raw_responses_dir) / task_id


def list_task_responses(task_id: str) -> list[dict]:
    """
    列出某任务目录下所有已保存的原始响应文件。

    Returns:
        list of dict, 每项包含 filename / size_bytes / saved_at
    """
    task_dir = get_task_response_dir(task_id)
    if not task_dir.exists():
        return []

    result = []
    for f in sorted(task_dir.glob("page_*.json")):
        stat = f.stat()
        result.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "saved_at": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        })
    return result


def list_all_tasks() -> list[dict]:
    """
    列出所有已保存原始响应的任务。

    Returns:
        list of dict, 每项包含 task_id / page_count / total_bytes / latest_at
    """
    base = Path(settings.raw_responses_dir)
    if not base.exists():
        return []

    result = []
    for task_dir in sorted(base.iterdir()):
        if not task_dir.is_dir():
            continue
        files = list(task_dir.glob("page_*.json"))
        if not files:
            continue
        total_bytes = sum(f.stat().st_size for f in files)
        latest_mtime = max(f.stat().st_mtime for f in files)
        result.append({
            "task_id": task_dir.name,
            "page_count": len(files),
            "total_bytes": total_bytes,
            "latest_at": datetime.fromtimestamp(
                latest_mtime, tz=timezone.utc
            ).isoformat(),
        })
    return result


def delete_task_responses(task_id: str) -> int:
    """
    删除某任务的所有原始响应文件（目录也一并删除）。

    Returns:
        删除的文件数量
    """
    import shutil

    task_dir = get_task_response_dir(task_id)
    if not task_dir.exists():
        return 0

    files = list(task_dir.glob("page_*.json"))
    count = len(files)
    shutil.rmtree(task_dir, ignore_errors=True)
    logger.info(f"已删除任务 {task_id} 的 {count} 个原始响应文件")
    return count


# ═══════════════════════════════════════════════════════════════════
#  回复原始响应存储
# ═══════════════════════════════════════════════════════════════════

def _get_reply_dir(task_id: str, tweet_id: str) -> Path:
    """获取指定任务+推文的回复响应存储目录（自动创建）"""
    task_dir = Path(settings.raw_responses_dir) / task_id / "replies" / tweet_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def save_reply_response(task_id: str, tweet_id: str, page_num: int, body: dict) -> Optional[str]:
    """
    保存推文回复的原始 TweetDetail 响应 JSON 到磁盘。

    存储路径：{raw_responses_dir}/{task_id}/replies/{tweet_id}/page_{n}_{ts}.json

    Args:
        task_id:  任务 ID
        tweet_id: 推文 ID
        page_num: 评论页码（从 1 开始）
        body:     原始响应 dict

    Returns:
        保存的文件绝对路径，若未开启则返回 None
    """
    if not settings.save_raw_responses:
        return None

    try:
        reply_dir = _get_reply_dir(task_id, tweet_id)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"page_{page_num:03d}_{ts}.json"
        file_path = reply_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)

        size_kb = file_path.stat().st_size / 1024
        logger.info(f"回复原始响应已保存: replies/{tweet_id}/{file_path.name} ({size_kb:.1f} KB)")
        return str(file_path)
    except Exception as e:
        logger.warning(f"保存回复原始响应失败（task_id={task_id}, tweet_id={tweet_id}, page={page_num}）: {e}")
        return None


def list_reply_responses(task_id: str, tweet_id: str) -> list[dict]:
    """列出某推文回复的所有已存储原始响应文件"""
    reply_dir = Path(settings.raw_responses_dir) / task_id / "replies" / tweet_id
    if not reply_dir.exists():
        return []
    result = []
    for f in sorted(reply_dir.glob("page_*.json")):
        stat = f.stat()
        result.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "saved_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    return result
