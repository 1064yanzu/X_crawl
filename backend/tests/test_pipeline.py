from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_crawl_pipeline_sentinel_only_does_not_break_queue_accounting():
    from crawler.pipeline import CrawlPipeline, _SENTINEL

    pipeline = CrawlPipeline(
        task_id="task-x",
        timeout=1.0,
        max_replies_per_tweet=20,
        reply_depth=2,
    )
    pipeline._queue.put(_SENTINEL)

    pipeline._reply_worker()

    assert pipeline._queue.unfinished_tasks == 0


def test_weibo_comment_pipeline_sentinel_only_does_not_break_queue_accounting():
    from crawler.pipeline import WeiboCommentPipeline, _SENTINEL

    pipeline = WeiboCommentPipeline(task_id="task-weibo")
    pipeline._queue.put(_SENTINEL)

    pipeline._comment_worker()

    assert pipeline._queue.unfinished_tasks == 0
