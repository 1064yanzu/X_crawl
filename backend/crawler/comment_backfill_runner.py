from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Optional

import api.services.task_manager as task_manager
from crawler.crawl_signals import ChallengeSignal, StopSignal

logger = logging.getLogger(__name__)


@dataclass
class CommentBackfillResult:
    tweets: list[dict]
    replies_fetched: int
    failed_records: list[dict]
    progress: dict


def run_comment_backfill_task(
    *,
    task_id: str,
    platform: str,
    max_replies_per_tweet: int,
    reply_depth: int,
    browser_instance=None,
    reply_browser_instance=None,
) -> CommentBackfillResult:
    task = task_manager.get_task_full(task_id)
    if not task:
        raise RuntimeError(f"任务不存在: {task_id}")

    tweets = _resolve_comment_backfill_tweets(task_id=task_id, task=task)
    if not tweets:
        raise RuntimeError("评论补采任务没有可处理的帖子")

    if platform == "weibo":
        return _run_weibo_comment_backfill(
            task_id=task_id,
            tweets=tweets,
            browser_instance=browser_instance,
        )
    return _run_x_comment_backfill(
        task_id=task_id,
        tweets=tweets,
        max_replies_per_tweet=max_replies_per_tweet,
        reply_depth=reply_depth,
        browser_instance=browser_instance,
        reply_browser_instance=reply_browser_instance,
    )


def _resolve_comment_backfill_tweets(*, task_id: str, task: dict) -> list[dict]:
    tweets = copy.deepcopy(task.get("tweets") or [])
    if tweets:
        return tweets

    source_task_id = _resolve_source_task_id(task_id=task_id, task=task)
    if not source_task_id:
        return []

    source_task = task_manager.get_task_full(source_task_id)
    if not source_task:
        raise RuntimeError(f"评论补采源任务不存在或不可读取: {source_task_id}")

    from fastapi import HTTPException

    from api.services.comment_backfill_task_source import analyze_comment_backfill_task

    try:
        analysis = analyze_comment_backfill_task(source_task)
    except HTTPException as exc:
        raise RuntimeError(f"评论补采源任务不可用于回源补采: {exc.detail}") from exc

    source_tweets = copy.deepcopy(analysis.tweets)
    if source_tweets:
        logger.info(
            "评论补采任务回源原始任务成功: task_id=%s, source_task_id=%s, posts=%s",
            task_id,
            source_task_id,
            len(source_tweets),
        )
        task_manager.set_task_seed_tweets(task_id, source_tweets, current_page=0)
    return source_tweets


def _resolve_source_task_id(*, task_id: str, task: dict) -> str:
    source_task_id = str(task.get("source_task_id") or "").strip()
    if source_task_id:
        return source_task_id

    inferred = _infer_legacy_source_task_id(task_id=task_id, task=task)
    if inferred:
        logger.info(
            "评论补采任务自动补全 source_task_id: task_id=%s, source_task_id=%s",
            task_id,
            inferred,
        )
        task_manager.update_task_source_task_id(task_id, inferred)
        return inferred
    return ""


def _infer_legacy_source_task_id(*, task_id: str, task: dict) -> str:
    if str(task.get("task_kind") or "") != "comment_backfill":
        return ""
    if task.get("source_file_name"):
        return ""

    keyword = str(task.get("keyword") or "").strip()
    platform = str(task.get("platform") or "").strip().lower()
    if not keyword or platform not in {"x", "weibo"}:
        return ""

    prefix = "微博 评论补采 · " if platform == "weibo" else "X 评论补采 · "
    if not keyword.startswith(prefix):
        return ""
    source_keyword = keyword[len(prefix):].strip()
    if not source_keyword:
        return ""

    current_created_at = str(task.get("created_at") or "")
    candidates = task_manager.list_tasks(include_payload=False)
    matched = [
        item for item in candidates
        if item.get("task_id") != task_id
        and item.get("task_kind") == "search"
        and item.get("status") == "done"
        and str(item.get("platform") or "").lower() == platform
        and str(item.get("keyword") or "").strip() == source_keyword
        and int(item.get("result_count") or 0) > 0
    ]
    if not matched:
        return ""

    # 优先选择创建时间早于评论补采任务、且离它最近的一条搜索任务；若没有，再退回最新的一条。
    earlier_or_equal = [
        item for item in matched
        if not current_created_at or str(item.get("created_at") or "") <= current_created_at
    ]
    if earlier_or_equal:
        earlier_or_equal.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return str(earlier_or_equal[0].get("task_id") or "")

    matched.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return str(matched[0].get("task_id") or "")


def _run_x_comment_backfill(
    *,
    task_id: str,
    tweets: list[dict],
    max_replies_per_tweet: int,
    reply_depth: int,
    browser_instance=None,
    reply_browser_instance=None,
) -> CommentBackfillResult:
    from config import settings
    from crawler.pipeline import CrawlPipeline

    task_manager.update_task_phase(task_id, "正在准备 X 评论补采任务...")
    baseline = _compute_backfill_progress(tweets)
    task_manager.update_comment_backfill_progress(task_id, baseline)

    tweet_index: dict[str, dict] = {}
    counted_ids = _processed_ids(tweets)
    processed_count = baseline["processed_posts"]
    working_tweets = _sort_tweets_by_reply_count(copy.deepcopy(tweets))
    logger.info("评论补采推文已按评论数降序排列: task_id=%s, 总计 %d 条", task_id, len(working_tweets))
    previous_reply_totals = {
        str(tweet.get("id") or ""): _count_reply_tree(tweet.get("replies") or [])
        for tweet in tweets
        if tweet.get("id")
    }

    tweets_for_fetch = []
    for tweet in working_tweets:
        if tweet.get("comment_backfill_failed"):
            tweet.pop("replies", None)
        tweet_id = str(tweet.get("id") or "")
        if tweet_id:
            tweet_index[tweet_id] = tweet
        tweets_for_fetch.append(tweet)

    def _on_reply_done(tweet_id: str, replies: list[dict]) -> None:
        nonlocal processed_count
        target = tweet_index.get(tweet_id)
        if target is not None:
            target["replies"] = replies
            target["comment_backfill_failed"] = False
        if tweet_id not in counted_ids:
            counted_ids.add(tweet_id)
            processed_count += 1
        delta_replies = max(0, _count_reply_tree(replies) - previous_reply_totals.get(tweet_id, 0))
        previous_reply_totals[tweet_id] = _count_reply_tree(replies)
        task_manager.update_task_phase(
            task_id,
            f"正在补采 X 评论（已处理 {processed_count}/{len(working_tweets)} 条）...",
        )
        if delta_replies > 0:
            task_manager.update_task_replies_progress(task_id, tweet_id, delta_replies)
        task_manager.update_comment_backfill_progress(
            task_id,
            {
                **baseline,
                "processed_posts": processed_count,
            },
        )
        task_manager.update_preview_tweets(task_id, processed_count, working_tweets)

    # ── Pipeline 解耦模式：reply_worker（一级）和 nested_worker（二级）并行 ──
    # 补采模式下可使用多个 reply_worker 并行抓取（没有搜索翻页，主实例可用）
    # reply_worker_count: 并行 reply worker 数（每个各自持有独立 tab）
    reply_worker_count = 2  # 补采默认 2 个并行 worker
    pipeline = CrawlPipeline(
        task_id=task_id,
        timeout=settings.crawler_timeout,
        max_replies_per_tweet=max_replies_per_tweet,
        reply_depth=reply_depth,
        browser_instance=browser_instance,
        reply_browser_instance=reply_browser_instance,
        on_reply_done=_on_reply_done,
        reply_worker_count=reply_worker_count,
    )
    pipeline.start()
    pipeline.put_batch(tweets_for_fetch)
    pipeline.finish_search()
    pipeline.join()
    pipeline.check_error()  # StopSignal / ChallengeSignal 重新抛出

    # 从 result_map 收集最终结果（已含二级评论）
    updated_tweets = []
    for tweet in working_tweets:
        tid = str(tweet.get("id") or "")
        updated_tweets.append(pipeline.result_map.get(tid, tweet))

    failed_records = list(pipeline.failed_records)
    failed_ids = {str(item.get("tweet_id") or "") for item in failed_records if item.get("tweet_id")}
    for tweet in updated_tweets:
        tweet["comment_backfill_failed"] = str(tweet.get("id") or "") in failed_ids

    progress = _compute_backfill_progress(updated_tweets)
    task_manager.update_comment_backfill_progress(task_id, progress)
    current_page = progress["processed_posts"]
    task_manager.update_preview_tweets(task_id, current_page, updated_tweets)

    return CommentBackfillResult(
        tweets=updated_tweets,
        replies_fetched=_count_nested_replies(updated_tweets),
        failed_records=failed_records,
        progress=progress,
    )


def _run_weibo_comment_backfill(
    *,
    task_id: str,
    tweets: list[dict],
    browser_instance=None,
) -> CommentBackfillResult:
    from config import settings
    from crawler.utils import check_signal, jittered_sleep
    from crawler.weibo.comment_fetcher import fetch_comments
    from crawler.weibo.comment_stats import build_comment_stats, collect_comment_tree_stats

    total = len(tweets)
    failed_records: list[dict] = []
    counted_ids = _processed_ids(tweets)
    working_tweets = _sort_tweets_by_reply_count(copy.deepcopy(tweets))
    logger.info("微博评论补采推文已按评论数降序排列: task_id=%s, 总计 %d 条", task_id, len(working_tweets))
    task_manager.update_task_phase(task_id, "正在准备微博评论补采任务...")
    task_manager.update_comment_backfill_progress(task_id, _compute_backfill_progress(working_tweets))

    for idx, tweet in enumerate(working_tweets):
        check_signal(task_id)
        tweet_id = str(tweet.get("id") or "")
        if tweet.get("replies") is not None and not tweet.get("comment_backfill_failed"):
            continue

        task_manager.update_task_phase(
            task_id,
            f"正在补采微博评论（{idx + 1}/{total}）...",
        )
        try:
            result = fetch_comments(
                mid=tweet_id,
                author_uid=str((tweet.get("author") or {}).get("id") or ""),
                post_url=str(tweet.get("url") or ""),
                post_comment_count=int((tweet.get("metrics") or {}).get("replies") or 0),
                max_comments=500,
                page_interval=settings.crawler_page_interval,
                task_id=task_id,
                browser_instance=browser_instance,
            )
            replies = [comment.to_dict() for comment in result.comments]
            tweet["replies"] = replies
            tweet["comment_backfill_failed"] = False
            tweet["comment_stats"] = build_comment_stats(
                post_comment_count=int((tweet.get("metrics") or {}).get("replies") or 0),
                api_claimed_total=result.api_claimed_total,
                fetched_total_count=result.fetched_total_count,
                fetched_top_level_count=result.fetched_top_level_count,
                max_depth=collect_comment_tree_stats(result.comments).max_depth,
                sub_comment_completion_status=result.sub_comment_completion_status,
                truncated_reason=result.truncated_reason,
                pages_fetched=result.pages_fetched,
            )
            task_manager.update_task_replies_progress(task_id, tweet_id, result.fetched_total_count)
        except StopSignal:
            raise
        except ChallengeSignal:
            raise
        except Exception as exc:
            logger.error("微博评论补采失败: task_id=%s, post_id=%s, error=%s", task_id, tweet_id, exc, exc_info=True)
            tweet["replies"] = []
            tweet["comment_backfill_failed"] = True
            failed_records.append(
                {
                    "task_id": task_id,
                    "tweet_id": tweet_id,
                    "screen_name": str((tweet.get("author") or {}).get("screen_name") or ""),
                    "expected_count": int((tweet.get("metrics") or {}).get("replies") or 0),
                    "fetched_count": 0,
                    "error_reason": f"异常: {str(exc)[:200]}",
                }
            )

        counted_ids.add(tweet_id)
        progress = _compute_backfill_progress(working_tweets)
        task_manager.update_comment_backfill_progress(task_id, progress)
        task_manager.update_preview_tweets(task_id, len(counted_ids), working_tweets)
        jittered_sleep(settings.crawler_page_interval, task_id=task_id)

    progress = _compute_backfill_progress(working_tweets)
    task_manager.update_comment_backfill_progress(task_id, progress)
    task_manager.update_preview_tweets(task_id, progress["processed_posts"], working_tweets)
    return CommentBackfillResult(
        tweets=working_tweets,
        replies_fetched=_count_nested_replies(working_tweets),
        failed_records=failed_records,
        progress=progress,
    )


def _sort_tweets_by_reply_count(tweets: list[dict]) -> list[dict]:
    """
    按预期评论数从高到低排序推文，优先采集高价值推文。
    已处理过（replies 不为 None）的推文排在最后，避免影响未处理推文的优先级。
    同评论数的推文保持原始顺序（稳定排序）。
    """
    def _sort_key(tweet: dict) -> tuple[int, int]:
        # 已处理的排最后
        already_done = 0 if tweet.get("replies") is None else 1
        # 评论数取负（高到低）
        reply_count = int((tweet.get("metrics") or {}).get("replies") or 0)
        return (already_done, -reply_count)

    return sorted(tweets, key=_sort_key)


def _processed_ids(tweets: list[dict]) -> set[str]:
    ids = set()
    for tweet in tweets:
        tweet_id = str(tweet.get("id") or "")
        if tweet_id and tweet.get("replies") is not None:
            ids.add(tweet_id)
    return ids


def _compute_backfill_progress(tweets: list[dict]) -> dict:
    total = len(tweets)
    processed = 0
    failed = 0
    for tweet in tweets:
        if tweet.get("replies") is not None:
            processed += 1
        if tweet.get("comment_backfill_failed"):
            failed += 1
    return {
        "total_posts": total,
        "eligible_posts": total,
        "processed_posts": processed,
        "skipped_posts": 0,
        "succeeded_posts": max(0, processed - failed),
        "failed_posts": failed,
    }


def _count_nested_replies(tweets: list[dict]) -> int:
    total = 0

    def _walk(nodes: list[dict]) -> None:
        nonlocal total
        for node in nodes:
            replies = node.get("replies") or []
            if not isinstance(replies, list):
                continue
            total += len(replies)
            _walk([reply for reply in replies if isinstance(reply, dict)])

    _walk(tweets)
    return total


def _count_reply_tree(replies: list[dict]) -> int:
    total = len(replies)
    for reply in replies:
        nested = reply.get("replies") or []
        if isinstance(nested, list) and nested:
            total += _count_reply_tree([node for node in nested if isinstance(node, dict)])
    return total
