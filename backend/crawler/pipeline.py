"""
crawler/pipeline.py — 三阶流水线

设计目标：
  search_browser → 不断翻页抓推文 → 每批 put 到 tweet_queue
  reply_worker   → 从 tweet_queue 取推文 → 抓一级回复 → put 到 nested_queue（如需二级）
  nested_worker  → 从 nested_queue 取推文 → 抓二级回复 → 写回 result_map

核心设计：
  - 搜索和一级回复使用独立浏览器实例，真正并行
  - 一级评论与二级评论解耦：一级抓完即入队二级，不在 reply_worker 内串行等待
  - 一级 worker 只负责 reply_depth=1 的抓取，完成后立即处理下一条推文
  - 二级 worker 在另一个 tab 串行消费，不阻塞一级 worker

搜索结束后：
  - finish_search() 发送结束哨兵到 tweet_queue
  - reply_worker 耗尽 tweet_queue 后再发送哨兵到 nested_queue
  - join() 等待两个 worker 线程都退出

数据安全：
  - 搜索线程每页抓到后立即 checkpoint（不等回复）
  - 回复线程每条完成后调用 on_reply_done callback 落盘
  - StopSignal / ChallengeSignal 发生时，两个线程都能感知并安全退出
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
    双浏览器并发流水线。

    搜索和回复分别使用独立的浏览器实例（独立 Chrome 进程 +
    独立 WebSocket 连接），确保搜索和回复拥取真正并行执行，
    不会因 CDP 命令串行化而交替执行。

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
        reply_browser_instance=None,
        nested_browser_instance=None,
        on_reply_done: Optional[Callable[[str, list[dict]], None]] = None,
        reply_worker_count: int = 1,
    ):
        """
        Args:
            task_id:                任务 ID（共享信号检查）
            timeout:                单个推文回复抓取超时（秒）
            max_replies_per_tweet:  每条推文最多抓取的回复数
            reply_depth:            回复层级深度（>1 时启用独立 nested_worker 抓二级评论）
            browser_instance:       搜索用浏览器池实例（备用）
            reply_browser_instance: L1 回复专用独立浏览器实例（独立 Chrome 进程）
            nested_browser_instance: L2 二级评论专用独立浏览器实例（完全与 L1 解耦）
            on_reply_done:          每条推文 L1 完成后立即回调 (tweet_id, replies)；
                                    L2 完成后再次回调以更新完整 replies。
            reply_worker_count:     reply_worker 并行数（补采模式可设为 2-3 提升效率）
        """
        self.task_id = task_id
        self.timeout = timeout
        self.max_replies_per_tweet = max_replies_per_tweet
        self.reply_depth = reply_depth
        self.browser_instance = browser_instance
        self.reply_browser_instance = reply_browser_instance
        self.nested_browser_instance = nested_browser_instance
        self.on_reply_done = on_reply_done
        self.reply_worker_count = max(1, reply_worker_count)

        # 一级评论队列：搜索线程 → reply_worker
        self._queue: queue.Queue = queue.Queue()
        # 二级评论队列：reply_worker → nested_worker（仅 reply_depth > 1 时使用）
        self._nested_queue: queue.Queue = queue.Queue()

        # tweet_id -> 附有 replies 的完整推文 dict
        self.result_map: dict[str, dict] = {}
        # 受保护的 result_map 写锁（reply_worker 和 nested_worker 都会写）
        self._result_map_lock = threading.Lock()
        self.failed_records: list[dict] = []
        self._failed_records_lock = threading.Lock()

        # 任意 worker 线程发生的致命异常
        self._error: Optional[Exception] = None
        self._error_lock = threading.Lock()

        self._reply_threads: list[threading.Thread] = []
        self._nested_thread: Optional[threading.Thread] = None
        self._reply_tab = None
        self._owns_reply_tab = False
        # 哨兵计数器：多 worker 模式下需要发送 N 个哨兵通知所有 worker 退出
        self._sentinel_count = 0

    # ─────────────────────────────────────────────────────────────────
    #  公共接口
    # ─────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """启动 reply worker（以及需要时的 nested worker）线程。"""
        for i in range(self.reply_worker_count):
            name = f"reply-worker-{(self.task_id or 'anon')[:8]}-{i}"
            t = threading.Thread(
                target=self._reply_worker,
                args=(i,),
                daemon=True,
                name=name,
            )
            t.start()
            self._reply_threads.append(t)
            logger.info(f"[Pipeline] reply worker #{i} 已启动: {name}")

        # reply_depth > 1 时，启动独立的 nested worker 处理二级评论
        if self.reply_depth > 1:
            nested_name = f"nested-worker-{(self.task_id or 'anon')[:8]}"
            self._nested_thread = threading.Thread(
                target=self._nested_worker,
                daemon=True,
                name=nested_name,
            )
            self._nested_thread.start()
            logger.info(f"[Pipeline] nested worker 已启动: {nested_name}")

    def put_batch(self, tweets: list[dict]) -> None:
        """搜索线程批量放入推文（非阻塞）。"""
        for tweet in tweets:
            self._queue.put(tweet)

    def finish_search(self) -> None:
        """搜索完成，发送结束哨兵，通知所有 reply worker 在耗尽队列后退出。"""
        for _ in range(self.reply_worker_count):
            self._queue.put(_SENTINEL)
        logger.debug("[Pipeline] 已发送 %d 个结束哨兵到 tweet_queue", self.reply_worker_count)

    def join(self) -> None:
        """等待所有 worker 线程结束。"""
        for t in self._reply_threads:
            t.join()
        if self._nested_thread is not None:
            self._nested_thread.join()
        self._cleanup_tabs()

    def check_error(self) -> None:
        """如果任意 worker 侧有致命异常，在搜索线程中重新抛出。"""
        with self._error_lock:
            if self._error is not None:
                raise self._error

    def get_error(self) -> Optional[Exception]:
        with self._error_lock:
            return self._error

    # ─────────────────────────────────────────────────────────────────
    #  内部实现
    # ─────────────────────────────────────────────────────────────────

    def _cleanup_tabs(self) -> None:
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

    def _ensure_reply_tab(self):
        if self._reply_tab is not None:
            return self._reply_tab

        if self.reply_browser_instance is not None:
            self._reply_tab = self.reply_browser_instance.new_tab()
        elif self.browser_instance is not None:
            logger.warning(
                "[Pipeline] 未提供独立 reply_browser_instance，"
                "回退为同实例新 tab（CDP 串行化，并发效率降低）"
            )
            self._reply_tab = self.browser_instance.new_tab()
        else:
            from crawler.browser import get_new_tab
            self._reply_tab = get_new_tab()
        self._owns_reply_tab = True
        return self._reply_tab

    def _drain_queue(self, q: queue.Queue) -> None:
        """清空指定队列（发生致命错误时调用，确保不挂起）。"""
        while True:
            try:
                q.get_nowait()
                q.task_done()
            except queue.Empty:
                break

    def _reply_worker(self, worker_id: int = 0) -> None:
        """
        一级评论 worker：从 tweet_queue 取推文，只抓一级评论（reply_depth=1），
        完成后把有子评论的一级评论推入 nested_queue 供 nested_worker 消费。
        多 worker 模式下每个 worker 各自持有独立的 reply tab。
        """
        from crawler.reply_fetcher import fetch_replies_single
        from crawler.crawl_signals import StopSignal, ChallengeSignal
        from crawler.utils import check_signal

        effective_browser = self.reply_browser_instance or self.browser_instance
        # 一级 worker 始终只抓第 1 层
        effective_depth = 1

        # 每个 worker 各自创建独立的 reply tab
        reply_tab = None
        owns_tab = False
        try:
            if effective_browser is not None:
                reply_tab = effective_browser.new_tab()
                owns_tab = True
            elif self.browser_instance is not None:
                reply_tab = self.browser_instance.new_tab()
                owns_tab = True
            else:
                from crawler.browser import get_new_tab
                reply_tab = get_new_tab()
                owns_tab = True
        except Exception as e:
            logger.error(f"[Pipeline] reply worker #{worker_id} 创建 tab 失败: {e}")
            # 回退：不创建 tab，走原有逻辑让 fetch_replies_single 自行创建
            reply_tab = None
            owns_tab = False

        logger.debug(f"[Pipeline] reply worker #{worker_id} 进入主循环")
        # 通知用户浏览器准备就绪，即将开始抓取评论
        try:
            import api.services.task_manager as _task_mgr
            _task_mgr.update_task_phase(
                self.task_id,
                f"浏览器就绪，开始抓取评论...",
            )
        except Exception:
            pass

        while True:
            try:
                item = self._queue.get(timeout=2.0)
            except queue.Empty:
                try:
                    check_signal(self.task_id)
                except (StopSignal, ChallengeSignal) as e:
                    self._set_error(e)
                    self._drain_queue(self._queue)
                    # 通知 nested_worker 退出（仅由遇到信号的 worker 发送一次）
                    if self.reply_depth > 1:
                        self._nested_queue.put(_SENTINEL)
                    logger.info(f"[Pipeline] reply worker #{worker_id} 收到信号，退出: {e}")
                    break
                continue

            should_exit = item is _SENTINEL
            should_drain = False
            tweet = item if item is not _SENTINEL else None
            tweet_id = str(tweet.get("id", "")) if isinstance(tweet, dict) else ""

            try:
                if should_exit:
                    logger.debug(f"[Pipeline] reply worker #{worker_id} 收到结束哨兵，退出主循环")
                    # 最后一个退出的 reply_worker 负责通知 nested_worker
                    with self._error_lock:
                        self._sentinel_count += 1
                        is_last = self._sentinel_count >= self.reply_worker_count
                    if is_last and self.reply_depth > 1:
                        self._nested_queue.put(_SENTINEL)
                else:
                    check_signal(self.task_id)

                    # 使用 worker 自己的 tab（多 worker 并行各自持有独立 tab）
                    effective_tab = reply_tab or self._ensure_reply_tab()

                    # 只抓一级评论（effective_depth=1）
                    updated_tweet, failure_info = fetch_replies_single(
                        tweet=tweet,
                        task_id=self.task_id,
                        timeout=self.timeout,
                        max_replies_per_tweet=self.max_replies_per_tweet,
                        reply_depth=effective_depth,
                        existing_tab=effective_tab,
                        browser_instance=effective_browser,
                    )

                    with self._result_map_lock:
                        self.result_map[tweet_id] = updated_tweet
                    if failure_info:
                        with self._failed_records_lock:
                            self.failed_records.append(failure_info)

                    # L1 完成后立即触发回调（进度对用户实时可见，不等二级评论）
                    if self.on_reply_done:
                        try:
                            self.on_reply_done(tweet_id, updated_tweet.get("replies") or [])
                        except Exception as cb_err:
                            logger.warning(f"[Pipeline] on_reply_done L1 回调异常: {cb_err}")

                    # 有二级评论需求时，把一级结果推入 nested_queue（L2 完成后再次触发回调以更新完整 replies）
                    if self.reply_depth > 1:
                        self._nested_queue.put(updated_tweet)

            except (StopSignal, ChallengeSignal) as e:
                self._set_error(e)
                should_exit = True
                should_drain = True
                logger.info(f"[Pipeline] reply worker #{worker_id} 遭遇致命信号，退出: {type(e).__name__}")
            except Exception as e:
                logger.error(
                    f"[Pipeline] 抓取 tweet_id={tweet_id} 一级回复时发生异常（跳过）: {e}",
                    exc_info=True,
                )
            finally:
                try:
                    self._queue.task_done()
                except ValueError:
                    pass
                if should_drain:
                    self._drain_queue(self._queue)
                    if self.reply_depth > 1:
                        self._nested_queue.put(_SENTINEL)

            if should_exit:
                break

        # 清理 worker 自己的 tab
        if owns_tab and reply_tab is not None:
            try:
                reply_tab.listen.stop()
            except Exception:
                pass
            try:
                reply_tab.close()
            except Exception:
                pass

        logger.debug(f"[Pipeline] reply worker #{worker_id} 退出主循环")

    def _nested_worker(self) -> None:
        """
        二级评论 worker：从 nested_queue 取已有一级评论的推文，
        对其中有子评论的一级评论再次抓取，不阻塞一级 worker。
        """
        from crawler.nested_reply_fetcher import fetch_nested_replies
        from crawler.crawl_signals import StopSignal, ChallengeSignal
        from crawler.utils import check_signal

        # L2 优先使用独立 nested_browser_instance（完全解耦于 L1），
        # 避免与 reply_worker 共用同一个浏览器实例产生 CDP 串行化竞争。
        effective_browser = self.nested_browser_instance or self.reply_browser_instance or self.browser_instance

        logger.debug("[Pipeline] nested worker 进入主循环")

        while True:
            try:
                item = self._nested_queue.get(timeout=2.0)
            except queue.Empty:
                try:
                    check_signal(self.task_id)
                except (StopSignal, ChallengeSignal) as e:
                    self._set_error(e)
                    self._drain_queue(self._nested_queue)
                    logger.info(f"[Pipeline] nested worker 收到信号，退出: {e}")
                    return
                continue

            should_exit = item is _SENTINEL
            should_drain = False
            tweet = item if item is not _SENTINEL else None
            tweet_id = str(tweet.get("id", "")) if isinstance(tweet, dict) else ""

            try:
                if should_exit:
                    logger.debug("[Pipeline] nested worker 收到结束哨兵，退出主循环")
                else:
                    check_signal(self.task_id)
                    replies = tweet.get("replies") or []
                    if not replies:
                        # 一级无评论，无需抓二级，直接触发回调
                        if self.on_reply_done:
                            try:
                                self.on_reply_done(tweet_id, [])
                            except Exception:
                                pass
                    else:
                        updated_replies, nested_failed = fetch_nested_replies(
                            replies,
                            current_depth=1,
                            max_depth=self.reply_depth,
                            max_replies_per_tweet=self.max_replies_per_tweet,
                            task_id=self.task_id,
                            timeout=self.timeout,
                            browser_instance=effective_browser,
                        )
                        updated_tweet = dict(tweet)
                        updated_tweet["replies"] = updated_replies

                        with self._result_map_lock:
                            self.result_map[tweet_id] = updated_tweet
                        if nested_failed:
                            with self._failed_records_lock:
                                self.failed_records.extend(nested_failed)

                        if self.on_reply_done:
                            try:
                                self.on_reply_done(tweet_id, updated_replies)
                            except Exception as cb_err:
                                logger.warning(f"[Pipeline] nested on_reply_done 回调异常: {cb_err}")

            except (StopSignal, ChallengeSignal) as e:
                self._set_error(e)
                should_exit = True
                should_drain = True
                logger.info(f"[Pipeline] nested worker 遭遇致命信号，退出: {type(e).__name__}")
            except Exception as e:
                logger.error(
                    f"[Pipeline] 抓取 tweet_id={tweet_id} 二级回复时发生异常（跳过）: {e}",
                    exc_info=True,
                )
            finally:
                try:
                    self._nested_queue.task_done()
                except ValueError:
                    pass
                if should_drain:
                    self._drain_queue(self._nested_queue)

            if should_exit:
                return

        logger.debug("[Pipeline] nested worker 退出主循环")

    def _set_error(self, exc: Exception) -> None:
        with self._error_lock:
            if self._error is None:
                self._error = exc


# ─────────────────────────────────────────────────────────────────────
#  微博评论并发流水线（WeiboCommentPipeline）
# ─────────────────────────────────────────────────────────────────────

class WeiboCommentPipeline:
    """
    微博双浏览器并发流水线。

    搜索和评论分别使用独立的浏览器实例（独立 Chrome 进程 +
    独立 WebSocket 连接），确保搜索和评论拥取真正并行执行。

    search_tab  → 翻页解析帖子 → put_batch(posts)
    comment_tab → 逐条从队列取帖子 → 抓评论 → result_map

    接口与 CrawlPipeline 对齐。
    """

    def __init__(
        self,
        *,
        task_id: Optional[str],
        browser_instance=None,
        comment_browser_instance=None,
        on_comment_done: Optional[Callable[[str, list], None]] = None,
    ):
        self.task_id = task_id
        self.browser_instance = browser_instance
        self.comment_browser_instance = comment_browser_instance
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
        """评论 worker 主循环，在独立线程中执行。使用独立浏览器实例确保与搜索并行。"""
        from config import settings
        from crawler.weibo.comment_fetcher import fetch_comments as do_fetch_comments
        from crawler.weibo.comment_stats import build_comment_stats, collect_comment_tree_stats
        from crawler.crawl_signals import StopSignal, ChallengeSignal
        from crawler.utils import check_signal

        # comment worker 使用独立的浏览器实例（如果有）
        effective_browser = self.comment_browser_instance or self.browser_instance

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

            should_exit = item is _SENTINEL
            should_drain = False
            post = item if item is not _SENTINEL else None
            # 支持 WeiboPost 对象或 dict（已转换的）
            try:
                if should_exit:
                    logger.debug("[WeiboCommentPipeline] comment worker 收到结束哨兵，退出主循环")
                else:
                    mid = getattr(post, "mid", None) or (post.get("mid") if isinstance(post, dict) else None) or ""
                    author_id = getattr(post, "author_id", None) or (post.get("author_id") if isinstance(post, dict) else None) or ""
                    post_url = getattr(post, "url", None) or (post.get("url") if isinstance(post, dict) else None) or ""
                    comments_count = getattr(post, "comments_count", 0) or (post.get("comments_count", 0) if isinstance(post, dict) else 0)

                    if not mid or comments_count == 0:
                        # 直接写入（无需抓评论）
                        post_dict = post.to_dict() if hasattr(post, "to_dict") else post
                        self.result_map[str(mid)] = post_dict
                    else:
                        check_signal(self.task_id)

                        comment_result = do_fetch_comments(
                            mid,
                            author_uid=author_id,
                            post_url=post_url,
                            post_comment_count=comments_count,
                            max_comments=settings.weibo_max_comments_per_post,
                            page_interval=settings.weibo_comment_page_interval,
                            task_id=self.task_id,
                            browser_instance=effective_browser,
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
                should_exit = True
                should_drain = True
                logger.info(f"[WeiboCommentPipeline] comment worker 遭遇致命信号，退出: {type(e).__name__}")
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
                if should_drain:
                    self._drain_queue()

            if should_exit:
                return

        logger.debug("[WeiboCommentPipeline] comment worker 退出主循环")

    def _set_error(self, exc: Exception) -> None:
        with self._error_lock:
            if self._error is None:
                self._error = exc
