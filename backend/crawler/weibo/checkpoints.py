from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from json_utils import dump_json


CHECKPOINTS_DIR = Path(__file__).parent.parent.parent / "checkpoints"


def load_checkpoint(task_id: Optional[str]) -> dict:
    """加载微博任务断点。"""
    if not task_id:
        return {}

    path = CHECKPOINTS_DIR / f"weibo_{task_id}.json"
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_checkpoint(task_id: Optional[str], state: dict) -> None:
    """保存微博任务断点。"""
    if not task_id:
        return

    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKPOINTS_DIR / f"weibo_{task_id}.json"
    path.write_text(dump_json(state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_page_checkpoint(
    *,
    keyword: str,
    next_page: int,
    posts: list[dict],
    start_date: Optional[str],
    end_date: Optional[str],
) -> dict:
    return {
        "mode": "page",
        "page": next_page,
        "posts": posts,
        "keyword": keyword,
        "start_date": start_date,
        "end_date": end_date,
    }


def build_date_split_checkpoint(
    *,
    keyword: str,
    start_date: str,
    end_date: str,
    date_ranges: list[tuple[str, str]],
    next_segment_index: int,
    posts: list[dict],
) -> dict:
    return {
        "mode": "date_split",
        "keyword": keyword,
        "start_date": start_date,
        "end_date": end_date,
        "date_ranges": [list(item) for item in date_ranges],
        "next_segment_index": next_segment_index,
        "posts": posts,
    }


def checkpoint_mode(checkpoint: Optional[dict]) -> str:
    if not checkpoint:
        return ""
    mode = str(checkpoint.get("mode") or "").strip()
    if mode:
        return mode
    return "page" if checkpoint.get("page") else ""


def checkpoint_posts(checkpoint: Optional[dict]) -> list[dict]:
    posts = checkpoint.get("posts") if checkpoint else []
    return posts if isinstance(posts, list) else []


def checkpoint_page(checkpoint: Optional[dict], default: int = 1) -> int:
    if not checkpoint:
        return default
    try:
        page = int(checkpoint.get("page", default))
    except (TypeError, ValueError):
        return default
    return max(default, page)


def checkpoint_next_segment_index(checkpoint: Optional[dict]) -> int:
    if not checkpoint:
        return 0
    try:
        index = int(checkpoint.get("next_segment_index", 0))
    except (TypeError, ValueError):
        return 0
    return max(0, index)


def checkpoint_date_ranges(checkpoint: Optional[dict]) -> list[tuple[str, str]]:
    raw_ranges = checkpoint.get("date_ranges") if checkpoint else []
    if not isinstance(raw_ranges, list):
        return []

    ranges: list[tuple[str, str]] = []
    for item in raw_ranges:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        start, end = item
        if isinstance(start, str) and isinstance(end, str) and start and end:
            ranges.append((start, end))
    return ranges


def same_query_scope(
    checkpoint: Optional[dict],
    *,
    keyword: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> bool:
    if not checkpoint:
        return False
    if str(checkpoint.get("keyword") or "").strip() != str(keyword or "").strip():
        return False
    if (checkpoint.get("start_date") or None) != (start_date or None):
        return False
    if (checkpoint.get("end_date") or None) != (end_date or None):
        return False
    return True
