"""
crawler/parallel_backfill_coordinator.py — 多 Pipeline 并行评论补采协调器

当评论补采任务组设置 concurrency > 1 时，本模块负责：
1. 将推文列表按 round-robin 交错分块（保证各 Pipeline 负载均衡）
2. 为每个 Pipeline 分配独立的浏览器实例
3. 启动 N 个 CrawlPipeline 并行处理
4. 通过线程安全回调聚合所有 Pipeline 的进度
5. 等待所有 Pipeline 完成并合并结果

所有 Pipeline 共享同一个 task_id → check_signal() 信号自动传播。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkerResource:
    """单个并发 Worker 的资源包：独立浏览器 + 账号"""
    account_id: str
    account_alias: str
    reply_browser: object  # BrowserInstance
    nested_browser: object | None  # BrowserInstance (L2)


@dataclass
class ParallelBackfillResult:
    """并行协调器的聚合结果"""
    tweets: list[dict] = field(default_factory=list)
    replies_fetched: int = 0
    failed_records: list[dict] = field(default_factory=list)
    progress: dict = field(default_factory=dict)


class ParallelBackfillCoordinator:
    """
    多 Pipeline 并行评论补采协调器。

    将排序后的推文列表 round-robin 分配给 N 个 CrawlPipeline，
    每个 Pipeline 使用独立的浏览器和 reply worker 线程。
    """

    def __init__(
        self,
        *,
        task_id: str,
        tweets: list[dict],
        worker_resources: list[WorkerResource],
        max_replies_per_tweet: int,
        reply_depth: int,
        on_progress: Optional[Callable[[dict], None]] = None,
        reply_worker_count_per_pipeline: int = 1,
    ):
        self.task_id = task_id
        self.tweets = tweets
        self.worker_resources = worker_resources
        self.n = len(worker_resources)
        self.max_replies_per_tweet = max_replies_per_tweet
        self.reply_depth = reply_depth
        self.on_progress = on_progress
        self.reply_worker_count_per_pipeline = reply_worker_count_per_pipeline

        # 线程安全的共享进度
        self._lock = threading.Lock()
        self._processed_count = 0
        self._counted_ids: set[str] = set()
        self._tweet_index: dict[str, dict] = {}

    def run(self) -> ParallelBackfillResult:
        """执行并行补采，阻塞直到所有 Pipeline 完成。"""
        from api.services import task_manager
        from config import settings
        from crawler.pipeline import CrawlPipeline

        # ── 初始化：按评论数排序后 round-robin 分块 ──
        from crawler.comment_backfill_runner import (
            _compute_backfill_progress,
            _processed_ids,
            _sort_tweets_by_reply_count,
        )

        working_tweets = _sort_tweets_by_reply_count(self.tweets)
        self._counted_ids = _processed_ids(working_tweets)
        self._processed_count = len(self._counted_ids)

        # 构建全局 tweet_index
        for tweet in working_tweets:
            tweet_id = str(tweet.get("id") or "")
            if tweet_id:
                self._tweet_index[tweet_id] = tweet

        # 清理之前失败的标记（会被重新抓取）
        tweets_for_fetch: list[list[dict]] = [[] for _ in range(self.n)]
        for i, tweet in enumerate(working_tweets):
            if tweet.get("comment_backfill_failed"):
                tweet.pop("replies", None)
            chunk_idx = i % self.n
            tweets_for_fetch[chunk_idx].append(tweet)

        total_tweets = len(working_tweets)
        chunk_sizes = [len(c) for c in tweets_for_fetch]
        logger.info(
            "并行协调器启动: task_id=%s, pipelines=%d, 总推文=%d, 分块=%s",
            self.task_id[:8], self.n, total_tweets, chunk_sizes,
        )

        # ── 初始进度 ──
        baseline = _compute_backfill_progress(working_tweets)
        task_manager.update_comment_backfill_progress(self.task_id, baseline)

        # ── 预热所有浏览器实例（避免 Pipeline 启动后并发触发浏览器启动风暴） ──
        task_manager.update_task_phase(
            self.task_id,
            f"正在预热 {self.n} 组浏览器实例...",
        )
        import time as _time
        for i, res in enumerate(self.worker_resources):
            try:
                # 触发懒初始化：调用 get_browser() 确保 Chrome 进程已就绪
                res.reply_browser.get_browser()
                logger.info("预热浏览器 reply #%d 完成", i)
            except Exception as e:
                logger.warning("预热浏览器 reply #%d 失败: %s", i, e)
            if res.nested_browser is not None:
                try:
                    res.nested_browser.get_browser()
                    logger.info("预热浏览器 nested #%d 完成", i)
                except Exception as e:
                    logger.warning("预热浏览器 nested #%d 失败: %s", i, e)
            # 错开启动，减少 CPU 峰值
            if i < self.n - 1:
                _time.sleep(2.0)

        # ── 共享回调（线程安全） ──
        def _on_reply_done(tweet_id: str, replies: list[dict]) -> None:
            with self._lock:
                target = self._tweet_index.get(tweet_id)
                if target is not None:
                    target["replies"] = replies
                    target["comment_backfill_failed"] = False
                if tweet_id not in self._counted_ids:
                    self._counted_ids.add(tweet_id)
                    self._processed_count += 1
                current = self._processed_count

            delta_replies = len(replies)
            task_manager.update_task_phase(
                self.task_id,
                f"正在并行补采 X 评论（{self.n} 路并发，已处理 {current}/{total_tweets} 条）...",
            )
            if delta_replies > 0:
                task_manager.update_task_replies_progress(self.task_id, tweet_id, delta_replies)

            progress = {
                **baseline,
                "processed_posts": current,
            }
            task_manager.update_comment_backfill_progress(self.task_id, progress)
            task_manager.update_preview_tweets(self.task_id, current, working_tweets)

            if self.on_progress:
                self.on_progress(progress)

        # ── 创建并启动 N 个 Pipeline ──
        pipelines: list[CrawlPipeline] = []
        task_manager.update_task_phase(
            self.task_id,
            f"正在启动 {self.n} 路并行评论抓取引擎（共 {total_tweets} 条帖子待处理）...",
        )

        for i, res in enumerate(self.worker_resources):
            pipeline = CrawlPipeline(
                task_id=self.task_id,
                timeout=settings.crawler_timeout,
                max_replies_per_tweet=self.max_replies_per_tweet,
                reply_depth=self.reply_depth,
                browser_instance=None,  # 不需要主浏览器
                reply_browser_instance=res.reply_browser,
                nested_browser_instance=res.nested_browser,
                on_reply_done=_on_reply_done,
                reply_worker_count=self.reply_worker_count_per_pipeline,
            )
            pipeline.start()
            pipeline.put_batch(tweets_for_fetch[i])
            pipeline.finish_search()
            pipelines.append(pipeline)
            logger.info(
                "Pipeline #%d 已启动: account=%s, 推文=%d",
                i, res.account_alias, len(tweets_for_fetch[i]),
            )

        # ── 等待所有 Pipeline 完成 ──
        for i, pipeline in enumerate(pipelines):
            pipeline.join()
            logger.info("Pipeline #%d 已完成: task_id=%s", i, self.task_id[:8])

        # ── 检查错误（StopSignal / ChallengeSignal） ──
        first_error: Exception | None = None
        for pipeline in pipelines:
            try:
                pipeline.check_error()
            except Exception as exc:
                if first_error is None:
                    first_error = exc

        # ── 合并结果 ──
        all_result_maps: dict[str, dict] = {}
        all_failed: list[dict] = []
        for pipeline in pipelines:
            all_result_maps.update(pipeline.result_map)
            all_failed.extend(pipeline.failed_records)

        # 从 result_map 收集最终推文
        updated_tweets = []
        for tweet in working_tweets:
            tid = str(tweet.get("id") or "")
            updated_tweets.append(all_result_maps.get(tid, tweet))

        # 标记失败记录
        failed_ids = {str(item.get("tweet_id") or "") for item in all_failed if item.get("tweet_id")}
        for tweet in updated_tweets:
            tweet["comment_backfill_failed"] = str(tweet.get("id") or "") in failed_ids

        final_progress = _compute_backfill_progress(updated_tweets)
        task_manager.update_comment_backfill_progress(self.task_id, final_progress)
        task_manager.update_preview_tweets(
            self.task_id, final_progress["processed_posts"], updated_tweets
        )

        logger.info(
            "并行协调器完成: task_id=%s, pipelines=%d, 处理=%d/%d, 失败=%d",
            self.task_id[:8], self.n,
            final_progress["processed_posts"], total_tweets,
            final_progress.get("failed_posts", 0),
        )

        # 如果有致命错误，在结果收集后重新抛出
        if first_error is not None:
            raise first_error

        return ParallelBackfillResult(
            tweets=updated_tweets,
            replies_fetched=_count_nested_replies(updated_tweets),
            failed_records=all_failed,
            progress=final_progress,
        )


def _count_nested_replies(tweets: list[dict]) -> int:
    """递归统计所有评论（含嵌套评论）总数。"""
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
