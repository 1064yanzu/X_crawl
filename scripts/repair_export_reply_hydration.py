from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from api.routers.export import _hydrate_tweets_for_export  # noqa: E402
from api.services import task_db, task_manager  # noqa: E402
from config import settings  # noqa: E402


def _resolve_db_path() -> Path:
    raw = Path(settings.tasks_db_path)
    if raw.is_absolute():
        return raw
    return BACKEND_DIR / raw


def main() -> int:
    db_path = _resolve_db_path()
    settings.tasks_db_path = str(db_path)
    raw_root = Path(settings.raw_responses_dir)
    if not raw_root.is_absolute():
        settings.raw_responses_dir = str(BACKEND_DIR / raw_root)
    task_db.init_db(db_path)
    task_manager._db_initialized = False
    task_manager._tasks.clear()
    task_manager._task_results.clear()
    task_manager._loaded_task_results.clear()
    task_manager._ensure_db()

    tasks = task_manager.list_tasks(include_payload=False)
    repaired_tasks = 0
    repaired_posts = 0

    for summary in tasks:
        platform = str(summary.get("platform") or "").lower()
        task_kind = str(summary.get("task_kind") or "")
        replies_fetched = int(summary.get("replies_fetched", 0) or 0)
        if platform != "x":
            continue
        if replies_fetched <= 0 and not summary.get("fetch_replies") and task_kind not in {
            "comment_backfill",
            "comment_backfill_group",
        }:
            continue

        payload = task_manager.get_task_export_payload(summary["task_id"])
        if not payload or not payload.get("tweets"):
            continue

        original_tweets = payload["tweets"]
        hydrated_tweets = _hydrate_tweets_for_export(payload, original_tweets)

        changed = 0
        for original, hydrated in zip(original_tweets, hydrated_tweets):
            if not isinstance(original, dict) or not isinstance(hydrated, dict):
                continue
            before = original.get("replies")
            after = hydrated.get("replies")
            if before is None and isinstance(after, list):
                changed += 1

        if changed <= 0:
            continue

        task_db.save_task_result(summary["task_id"], hydrated_tweets)
        repaired_tasks += 1
        repaired_posts += changed
        print(
            json.dumps(
                {
                    "task_id": summary["task_id"],
                    "keyword": summary.get("keyword", ""),
                    "repaired_posts": changed,
                },
                ensure_ascii=False,
            )
        )

    print(
        json.dumps(
            {
                "db_path": str(db_path),
                "repaired_tasks": repaired_tasks,
                "repaired_posts": repaired_posts,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
