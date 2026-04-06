#!/usr/bin/env python3
"""
从已存储的 X 原始响应中恢复被误删的任务。

默认行为：
- 仅恢复 `backend/raw_responses/` 下存在、但 `backend/tasks.db` 中缺失的 X 任务
- 关键词 / product / segment_progress 等元数据优先取 checkpoint
- 主搜索结果从 SearchTimeline 原始响应解析
- 回复从 `replies/<tweet_id>/page_*.json` 解析并回挂到对应主推文
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from api.services import task_db  # noqa: E402
from api.services.task_insights import summarize_tweets  # noqa: E402
from config import settings  # noqa: E402
from crawler.parser import parse_search_response  # noqa: E402
from crawler.reply_parser import parse_tweet_detail_response  # noqa: E402


def _resolve_backend_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else BACKEND_DIR / path


DB_PATH = _resolve_backend_path(settings.tasks_db_path)
RAW_ROOT = _resolve_backend_path(settings.raw_responses_dir)
CHECKPOINT_ROOT = BACKEND_DIR / "checkpoints"


def _file_mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _parse_page_number(path: Path) -> int:
    match = re.match(r"page_(\d+)_", path.name)
    return int(match.group(1)) if match else 0


def _parse_range_from_keyword(keyword: str) -> tuple[Optional[str], Optional[str]]:
    since_match = re.search(r"\bsince:(\S+)", keyword)
    until_match = re.search(r"\buntil:(\S+)", keyword)
    return (
        since_match.group(1) if since_match else None,
        until_match.group(1) if until_match else None,
    )


def _normalize_for_merge(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _merge_tweet_versions(existing: dict, incoming: dict) -> dict:
    merged = deepcopy(existing if len(existing.get("replies") or []) >= len(incoming.get("replies") or []) else incoming)
    merged_replies = _deduplicate_tweets((existing.get("replies") or []) + (incoming.get("replies") or []))
    if merged_replies:
        merged["replies"] = merged_replies
    return merged


def _deduplicate_tweets(tweets: Iterable[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    ordered_ids: list[str] = []

    for tweet in tweets:
        tweet_id = str(tweet.get("id") or "")
        if not tweet_id:
            continue
        current = deepcopy(tweet)
        if tweet_id not in seen:
            seen[tweet_id] = current
            ordered_ids.append(tweet_id)
            continue
        seen[tweet_id] = _merge_tweet_versions(seen[tweet_id], current)

    return [seen[tweet_id] for tweet_id in ordered_ids]


def _load_checkpoint(task_id: str) -> dict:
    checkpoint_path = CHECKPOINT_ROOT / f"{task_id}.json"
    if not checkpoint_path.exists():
        return {}
    return json.loads(checkpoint_path.read_text(encoding="utf-8"))


def _restore_task_payload(task_dir: Path) -> Optional[dict]:
    task_id = task_dir.name
    checkpoint = _load_checkpoint(task_id)
    if task_id.startswith("weibo_") or task_id.startswith("test-"):
        return None
    if not checkpoint:
        return None

    search_files = sorted(task_dir.glob("page_*.json"))
    if not search_files:
        return None

    all_tweets: list[dict] = []
    touched_files: list[Path] = list(search_files)

    for path in search_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        tweets, _bottom_cursor, _top_cursor = parse_search_response(payload)
        all_tweets.extend(tweets)

    unique_tweets = _deduplicate_tweets(all_tweets)
    tweet_map = {str(tweet.get("id")): tweet for tweet in unique_tweets if tweet.get("id")}

    replies_root = task_dir / "replies"
    if replies_root.exists():
        for reply_dir in sorted(p for p in replies_root.iterdir() if p.is_dir()):
            reply_files = sorted(reply_dir.glob("page_*.json"))
            if not reply_files or reply_dir.name not in tweet_map:
                continue
            touched_files.extend(reply_files)
            replies: list[dict] = []
            for reply_file in reply_files:
                payload = json.loads(reply_file.read_text(encoding="utf-8"))
                _focal, parsed_replies, _bottom, _top, _has_spam_boundary = parse_tweet_detail_response(
                    payload,
                    focal_tweet_id=reply_dir.name,
                )
                replies.extend(parsed_replies)
            if replies:
                current = tweet_map[reply_dir.name].get("replies") or []
                tweet_map[reply_dir.name]["replies"] = _deduplicate_tweets(current + replies)

    unique_tweets = [tweet_map[str(tweet.get("id"))] for tweet in unique_tweets if tweet.get("id")]
    replies_fetched, time_coverage = summarize_tweets(unique_tweets)

    keyword = checkpoint.get("root_keyword") or checkpoint.get("keyword") or task_id
    keyword = _normalize_for_merge(keyword)
    product = checkpoint.get("product") or "Top"
    start_date, end_date = _parse_range_from_keyword(keyword)
    checkpoint_saved_at = checkpoint.get("saved_at")
    created_at = min(_file_mtime_iso(path) for path in touched_files)
    finished_candidates = [_file_mtime_iso(path) for path in touched_files]
    if checkpoint_saved_at:
        finished_candidates.append(checkpoint_saved_at)
    finished_at = max(finished_candidates)

    return {
        "task_id": task_id,
        "status": "stopped" if checkpoint.get("next_cursor") else "done",
        "keyword": keyword,
        "product": product,
        "platform": "x",
        "max_count": max(len(unique_tweets), 1),
        "result_count": len(unique_tweets),
        "current_page": checkpoint.get("page_fetched") or max(_parse_page_number(path) for path in search_files),
        "created_at": created_at,
        "finished_at": finished_at,
        "error": None,
        "risk_state": "none",
        "quality_state": "complete",
        "runtime_metrics": {},
        "time_coverage": time_coverage,
        "last_event_at": finished_at,
        "resumed": False,
        "fetch_replies": replies_root.exists(),
        "max_replies_per_tweet": 0,
        "reply_depth": 2,
        "crawl_strategy": "dfs",
        "replies_fetched": replies_fetched,
        "crawl_phase": "已从原始响应恢复",
        "task_kind": "search",
        "source_file_name": None,
        "source_task_id": None,
        "queue_id": None,
        "queue_name": None,
        "queue_order": None,
        "queue_total": None,
        "comment_backfill_progress": {},
        "segment_progress": checkpoint.get("segment_progress") or {},
        "preview_tweets": deepcopy(unique_tweets[:10]),
        "start_date": checkpoint.get("segments", [{}])[0].get("since") if checkpoint.get("segments") else start_date,
        "end_date": checkpoint.get("segments", [{}])[-1].get("until") if checkpoint.get("segments") else end_date,
        "tweets": unique_tweets,
    }


def _existing_task_ids(db_path: Path) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT task_id FROM tasks").fetchall()
    return {row[0] for row in rows}


def _backup_db(db_path: Path) -> Path:
    backup_path = db_path.with_suffix(f".restore-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.db")
    shutil.copy2(db_path, backup_path)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description="从 X 原始响应恢复缺失任务")
    parser.add_argument("--task-id", action="append", help="仅恢复指定 task_id，可重复传入")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将恢复的任务，不写数据库")
    args = parser.parse_args()

    task_db.init_db(DB_PATH)
    existing_ids = _existing_task_ids(DB_PATH)
    candidate_dirs = sorted(path for path in RAW_ROOT.iterdir() if path.is_dir())

    if args.task_id:
        wanted = set(args.task_id)
        candidate_dirs = [path for path in candidate_dirs if path.name in wanted]
    else:
        candidate_dirs = [path for path in candidate_dirs if path.name not in existing_ids]

    restored_payloads: list[dict] = []
    for task_dir in candidate_dirs:
        payload = _restore_task_payload(task_dir)
        if payload is None:
            continue
        restored_payloads.append(payload)

    if not restored_payloads:
        print("没有发现需要恢复的 X 任务。")
        return 0

    if args.dry_run:
        for payload in restored_payloads:
            print(
                f"[dry-run] {payload['task_id']} "
                f"status={payload['status']} result_count={payload['result_count']} "
                f"keyword={payload['keyword']}"
            )
        print(f"\n共找到 {len(restored_payloads)} 个可恢复任务。")
        return 0

    backup_path = _backup_db(DB_PATH)
    for payload in restored_payloads:
        task_db.save_task(payload)

    print(f"数据库备份已创建: {backup_path}")
    print(f"已恢复 {len(restored_payloads)} 个 X 任务：")
    for payload in restored_payloads:
        print(
            f"- {payload['task_id']} "
            f"[{payload['status']}] "
            f"{payload['result_count']} 条 · {payload['keyword']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
