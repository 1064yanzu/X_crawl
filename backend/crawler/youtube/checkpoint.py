"""
YouTube 爬取任务的检查点读写。

断点结构：
{
  "mode": "keyword_search" | "channel_uploads" | "video_urls",
  "keyword": "...",                 # 关键词搜索使用
  "channel_id": "...",              # 频道任务使用
  "video_ids_signature": "...",     # video_urls 模式使用（对去重后 id 排序拼接 hash）
  "search_next_page_token": "...",  # 搜索/播放列表下一页 token（video_urls 模式不用）
  "search_pages_fetched": int,
  "collected_video_ids": [...],     # 去重
  "videos": [tweet_dict, ...],      # 已落盘的视频（含详情/评论）
  "pending_comment_video_ids": [...], # 还需抓评论的 video ID
  "completed_comment_video_ids": [...], # 已抓完评论的 ID
  "saved_at": "ISO"
}
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from json_utils import dump_json
from config import resolve_data_path

logger = logging.getLogger(__name__)


def _checkpoint_dir() -> Path:
    return resolve_data_path("checkpoints")


def _path_for(task_id: str) -> Path:
    d = _checkpoint_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"youtube_{task_id}.json"


def compute_video_ids_signature(video_ids: Iterable[str]) -> str:
    """对 video_urls 模式的输入 id 列表计算稳定签名：去重 + 排序 + sha1。"""
    dedup = sorted({str(v).strip() for v in (video_ids or []) if str(v).strip()})
    if not dedup:
        return ""
    return hashlib.sha1("\n".join(dedup).encode("utf-8")).hexdigest()


def load_checkpoint(task_id: Optional[str]) -> dict:
    if not task_id:
        return {}
    path = _path_for(task_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("YouTube 断点加载失败 task_id=%s: %s", task_id, exc)
        return {}


def save_checkpoint(task_id: Optional[str], state: dict) -> None:
    if not task_id:
        return
    try:
        state = dict(state or {})
        state["saved_at"] = datetime.now(timezone.utc).isoformat()
        path = _path_for(task_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(dump_json(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        logger.error("YouTube 断点保存失败 task_id=%s: %s", task_id, exc, exc_info=True)


def same_scope(
    checkpoint: dict,
    *,
    mode: str,
    keyword: str = "",
    channel_id: str = "",
    video_ids_signature: str = "",
) -> bool:
    if not checkpoint:
        return False
    if str(checkpoint.get("mode") or "") != mode:
        return False
    if mode == "keyword_search":
        return str(checkpoint.get("keyword") or "") == str(keyword or "")
    if mode == "channel_uploads":
        return str(checkpoint.get("channel_id") or "") == str(channel_id or "")
    if mode == "video_urls":
        return (
            str(checkpoint.get("video_ids_signature") or "")
            == str(video_ids_signature or "")
        )
    return False


def build_state(
    *,
    mode: str,
    keyword: str = "",
    channel_id: str = "",
    video_ids_signature: str = "",
    search_next_page_token: Optional[str] = None,
    search_pages_fetched: int = 0,
    collected_video_ids: Optional[list[str]] = None,
    videos: Optional[list[dict]] = None,
    pending_comment_video_ids: Optional[list[str]] = None,
    completed_comment_video_ids: Optional[list[str]] = None,
) -> dict:
    return {
        "mode": mode,
        "keyword": keyword or "",
        "channel_id": channel_id or "",
        "video_ids_signature": video_ids_signature or "",
        "search_next_page_token": search_next_page_token,
        "search_pages_fetched": int(search_pages_fetched or 0),
        "collected_video_ids": list(collected_video_ids or []),
        "videos": list(videos or []),
        "pending_comment_video_ids": list(pending_comment_video_ids or []),
        "completed_comment_video_ids": list(completed_comment_video_ids or []),
    }
