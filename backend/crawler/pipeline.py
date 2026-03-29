"""
crawler/pipeline.py — 双 Tab 并发流水线（B 方案）

设计目标：
  search_tab  → 不断翻页抓推文 → 每批 put 到 tweet_queue
  reply_tab   → 不断从 tweet_queue 取推文 → 抓回复 → 写回 result_map

搜索结束后：
  - search_tab 关闭监听
  - finish_search() 发送结束哨兵
  - join() 等待 reply 线程耗尽 queue

数据安全：
  - 搜索线程每页抓到后立即 checkpoint（不等回复）
  - 回复线程每条完成后调用 on_reply_done callback 落盘
  - StopSignal / ChallengeSignal 发生时，两个线程都能感知并安全退出
    - 搜索侧：check_signal() 自然抛出
    - 回复侧：check_signal() 抛出 → 存入 _error → join() 之后再次抛出
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 结束哨兵：搜索线程发完全部推文后放一个哨兵，通知 reply worker 退出
_SENTINEL = object()


class CrawlPipeline:
    """
    双 Tab 并发流水线。

    使用方式（在搜索线程中）：
        pipeline = CrawlPipeline(task_id=..., ...)
        pipeline.start()                    # 启动 reply worker 线程

        for batch in search_pages:
            pipeline.put_batch(batch)       # 非阻塞，立即返回

        pipeline.finish_search()            # 发送结束哨兵
        pipeline.join()                     # 等待 reply worker 耗尽队列

        pipeline.check_error()              # 如果 reply 侧有致命异常，此处重新抛出

        # 从 result_map 取回附带 replies 的推文
        for tweet in all_tweets:
            tid = str(tweet.get("id", ""))
            if tid in pipeline.result_map:
                tweet_with_replies = pipeline.result_map[tid]
    """

    def __init__(
        self,
        *,
        task_id: Optional[str],
        timeout: float,
        max_replies_per_tweet: int,
        reply_depth: int,
        browser_instance=None,
        on_reply_done: Optional[Callable[[str, list[dict]], None]] = None,
    ):
        """
        Args:
            task_id:               任务 ID（共享信号检查）
            timeout:               单个推文回复抓取超时（秒）
            max_replies_per_tweet: 每条推文最多抓取的回复数
            reply_depth:           回复层级深度
            browser_instance:      浏览器池实例（None = 使用默认全局浏览器）
            on_reply_done:         每条推文回复抓取完成后的回调 (tweet_id, replies)
        """
        self.task_id = task_id
        self.timeout = timeout
        self.max_replies_per_tweet = max_replies_per_tweet
        self.reply_depth = reply_depth
        self.browser_instance = browser_instance
        self.on_reply_done = on_reply_done

        self._queue: queue.Queue = queue.Queue()
        # tweet_id -> 附有 replies 的完整推文 dict
        self.result_map: dict[str, dict] = {}
        self.failed_records: list[dict] = []

        # reply worker 线程发生的致命异常（StopSignal / ChallengeSignal）
        self._error: Optional[Exception] = None
        self._error_lock = threading.Lock()

        self._reply_thread: Optional[threading.Thread] = None
        self._reply_tab = None
        self._owns_reply_tab = False

    # ─────────────────────────────────────────────────────────────────
    #  公共接口
    # ─────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """启动 reply worker 线程，并分配专属 reply_tab。"""
        if self.browser_instance is not None:
            self._reply_tab = self.browser_instance.new_tab()
        else:
            from crawler.browser import get_new_tab
            self._reply_tab = get_new_tab()
        self._owns_reply_tab = True

        name = f"reply-worker-{(self.task_id or 'anon')[:8]}"
        self._reply_thread = threading.Thread(
            target=self._reply_worker,
            daemon=True,
            name=name,
        )
        self._reply_thread.start()
        logger.info(f"[Pipeline] reply worker 已启动: {name}")

    def put_batch(self, tweets: list[dict]) -> None:
        """搜索线程批量放入推文（非阻塞）。"""
        for tweet in tweets:
            self._queue.put(tweet)

    def finish_search(self) -> None:
        """搜索完成，发送结束哨兵，通知 reply worker 在耗尽队列后退出。"""
        self._queue.put(_SENTINEL)
        logger.debug("[Pipeline] 已发送结束哨兵")

    def join(self) -> None:
        """等待 reply worker 线程结束（队列耗尽 + 哨兵处理完）。"""
        if self._reply_thread is not None:
            self._reply_thread.join()
        self._cleanup_reply_tab()

    def check_error(self) -> None:
        """如果 reply 侧有致命异常，在搜索线程中重新抛出。"""
        with self._error_lock:
            if self._error is not None:
                raise self._error

    def get_error(self) -> Optional[Exception]:
        with self._error_lock:
            return self._error

    # ─────────────────────────────────────────────────────────────────
    #  内部实现
    # ─────────────────────────────────────────────────────────────────

    def _cleanup_reply_tab(self) -> None:
        if self._owns_reply_tab and self._reply_tab is not None:
            try:
                self._reply_tab.listen.stop()
            except Exception:
                pass
            try:
                self._reply_tab.close()
            except Exception:
                pass
            self._reply_tab = None
            self._owns_reply_tab = False

    def _drain_queue(self) -> None:
        """清空队列（发生致命错误时调用，确保不挂起）。"""
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def _reply_worker(self) -> None:
        """reply worker 主循环，在独立线程中执行。"""
        from crawler.reply_fetcher import fetch_replies_single
        from crawler.crawl_signals import StopSignal, ChallengeSignal
        from crawler.utils import check_signal

        logger.debug("[Pipeline] reply worker 进入主循环")

        while True:
            try:
                item = self._queue.get(timeout=2.0)
            except queue.Empty:
                # 超时重试（检查是否有信号）
                try:
                    check_signal(self.task_id)
                except (StopSignal, ChallengeSignal) as e:
                    self._set_error(e)
                    self._drain_queue()
                    logger.info(f"[Pipeline] reply worker 收到信号，退出: {e}")
                    return
                continue

            # 收到结束哨兵
            if item is _SENTINEL:
                self._queue.task_done()
                logger.debug("[Pipeline] reply worker 收到结束哨兵，退出主循环")
                break

            tweet = item
            tweet_id = str(tweet.get("id", ""))

            try:
                # 检查任务信号（pause/stop）
                check_signal(self.task_id)

                updated_tweet, failure_info = fetch_replies_single(
                    tweet=tweet,
                    task_id=self.task_id,
                    timeout=self.timeout,
                    max_replies_per_tweet=self.max_replies_per_tweet,
                    reply_depth=self.reply_depth,
                    existing_tab=self._reply_tab,
                    browser_instance=self.browser_instance,
                )

                self.result_map[tweet_id] = updated_tweet
                if failure_info:
                    self.failed_records.append(failure_info)

                if self.on_reply_done:
                    try:
                        self.on_reply_done(tweet_id, updated_tweet.get("replies") or [])
                    except Exception as cb_err:
                        logger.warning(f"[Pipeline] on_reply_done 回调异常: {cb_err}")

            except (StopSignal, ChallengeSignal) as e:
                self._set_error(e)
                self._queue.task_done()
                self._drain_queue()
                logger.info(f"[Pipeline] reply worker 遭遇致命信号，退出: {type(e).__name__}")
                return
            except Exception as e:
                logger.error(
                    f"[Pipeline] 抓取 tweet_id={tweet_id} 回复时发生异常（跳过）: {e}",
                    exc_info=True,
                )
            finally:
                # 无论如何都要 task_done，避免 Queue.join() 永远阻塞
                try:
                    self._queue.task_done()
                except ValueError:
                    pass

        logger.debug("[Pipeline] reply worker 退出主循环")

    def _set_error(self, exc: Exception) -> None:
        with self._error_lock:
            if self._error is None:
                self._error = exc


# ─────────────────────────────────────────────────────────────────────
#  微博评论并发流水线（WeiboCommentPipeline）
# ─────────────────────────────────────────────────────────────────────

class WeiboCommentPipeline:
    """
    微博双 Tab 并发流水线。

    search_tab  → 翻页解析帖子 → put_batch(posts)
    comment_tab → 逐条从队列取帖子 → 抓评论 → result_map

    接口与 CrawlPipeline 对齐。
    """

    def __init__(
        self,
        *,
        task_id: Optional[str],
        browser_instance=None,
        on_comment_done: Optional[Callable[[str, list], None]] = None,
    ):
        self.task_id = task_id
        self.browser_instance = browser_instance
        self.on_comment_done = on_comment_done

        self._queue: queue.Queue = queue.Queue()
        # post_mid -> 附有 comments 的完整帖子 dict
        self.result_map: dict[str, dict] = {}

        self._error: Optional[Exception] = None
        self._error_lock = threading.Lock()

        self._comment_thread: Optional[threading.Thread] = None
        self._comment_tab = None
        self._owns_comment_tab = False

    def start(self) -> None:
        if self.browser_instance is not None:
            self._comment_tab = self.browser_instance.new_tab()
        else:
            from crawler.browser import get_new_tab
            self._comment_tab = get_new_tab()
        self._owns_comment_tab = True

        name = f"comment-worker-{(self.task_id or 'anon')[:8]}"
        self._comment_thread = threading.Thread(
            target=self._comment_worker,
            daemon=True,
            name=name,
        )
        self._comment_thread.start()
        logger.info(f"[WeiboCommentPipeline] comment worker 已启动: {name}")

    def put_batch(self, posts: list) -> None:
        """放入一批微博帖子（WeiboPost 或 dict）。"""
        for post in posts:
            self._queue.put(post)

    def finish_search(self) -> None:
        self._queue.put(_SENTINEL)
        logger.debug("[WeiboCommentPipeline] 已发送结束哨兵")

    def join(self) -> None:
        if self._comment_thread is not None:
            self._comment_thread.join()
        self._cleanup_comment_tab()

    def check_error(self) -> None:
        with self._error_lock:
            if self._error is not None:
                raise self._error

    def get_error(self) -> Optional[Exception]:
        with self._error_lock:
            return self._error

    def _cleanup_comment_tab(self) -> None:
        if self._owns_comment_tab and self._comment_tab is not None:
            try:
                self._comment_tab.close()
            except Exception:
                pass
            self._comment_tab = None
            self._owns_comment_tab = False

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def _comment_worker(self) -> None:
        """comment worker 主循环，在独立线程中执行。"""
        from config import settings
        from crawler.weibo.comment_fetcher import fetch_comments as do_fetch_comments
        from crawler.weibo.comment_stats import build_comment_stats, collect_comment_tree_stats
        from crawler.crawl_signals import StopSignal, ChallengeSignal
        from crawler.utils import check_signal

        logger.debug("[WeiboCommentPipeline] comment worker 进入主循环")

        while True:
            try:
                item = self._queue.get(timeout=2.0)
            except queue.Empty:
                try:
                    check_signal(self.task_id)
                except (StopSignal, ChallengeSignal) as e:
                    self._set_error(e)
                    self._drain_queue()
                    return
                continue

            if item is _SENTINEL:
                self._queue.task_done()
                break

            post = item
            # 支持 WeiboPost 对象或 dict（已转换的）
            try:
                mid = getattr(post, "mid", None) or (post.get("mid") if isinstance(post, dict) else None) or ""
                author_id = getattr(post, "author_id", None) or (post.get("author_id") if isinstance(post, dict) else None) or ""
                post_url = getattr(post, "url", None) or (post.get("url") if isinstance(post, dict) else None) or ""
                comments_count = getattr(post, "comments_count", 0) or (post.get("comments_count", 0) if isinstance(post, dict) else 0)

                if not mid or comments_count == 0:
                    # 直接写入（无需抓评论）
                    post_dict = post.to_dict() if hasattr(post, "to_dict") else post
                    self.result_map[str(mid)] = post_dict
                    self._queue.task_done()
                    continue

                check_signal(self.task_id)

                comment_result = do_fetch_comments(
                    mid,
                    author_uid=author_id,
                    post_url=post_url,
                    post_comment_count=comments_count,
                    max_comments=settings.weibo_max_comments_per_post,
                    page_interval=settings.weibo_comment_page_interval,
                    task_id=self.task_id,
                    browser_instance=self.browser_instance,
                )

                # 附加评论到帖子
                if hasattr(post, "comments"):
                    post.comments = comment_result.comments
                    tree_stats = collect_comment_tree_stats(comment_result.comments)
                    post.comment_stats = build_comment_stats(
                        post_comment_count=comments_count,
                        api_claimed_total=comment_result.api_claimed_total,
                        fetched_total_count=tree_stats.total_count,
                        fetched_top_level_count=tree_stats.top_level_count,
                        max_depth=tree_stats.max_depth,
                        sub_comment_completion_status=comment_result.sub_comment_completion_status,
                        truncated_reason=comment_result.truncated_reason,
                        pages_fetched=comment_result.pages_fetched,
                    )
                    post_dict = post.to_dict()
                else:
                    # 已经是 dict
                    post_dict = dict(post)
                    post_dict["comments"] = comment_result.comments

                self.result_map[str(mid)] = post_dict

                if self.on_comment_done:
                    try:
                        self.on_comment_done(str(mid), comment_result.comments)
                    except Exception:
                        pass

            except (StopSignal, ChallengeSignal) as e:
                self._set_error(e)
                self._queue.task_done()
                self._drain_queue()
                logger.info(f"[WeiboCommentPipeline] comment worker 遭遇致命信号，退出: {type(e).__name__}")
                return
            except Exception as e:
                logger.error(
                    f"[WeiboCommentPipeline] 抓取 mid={getattr(post, 'mid', '?')} 评论时发生异常（跳过）: {e}",
                    exc_info=True,
                )
            finally:
                try:
                    self._queue.task_done()
                except ValueError:
                    pass

        logger.debug("[WeiboCommentPipeline] comment worker 退出主循环")

    def _set_error(self, exc: Exception) -> None:
        with self._error_lock:
            if self._error is None:
                self._error = exc
