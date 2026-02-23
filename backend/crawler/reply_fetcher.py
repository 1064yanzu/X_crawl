"""
回复抓取器模块（v2 - 支持信号中断 + 更充分的等待）

变更：
- 每次翻页后额外等待 crawler_reply_wait 秒，确保评论区内容完全加载
- 支持任务控制信号检查（通过 task_id 传入），可随时终止
- 翻页间隔引入随机扰动，模拟人工操作
"""
import time
import random
import logging
from typing import Optional

from crawler.browser import get_new_tab
from crawler.reply_parser import parse_tweet_detail_response, TWEET_DETAIL_PATTERN
from crawler.response_saver import save_reply_response
from crawler.page_health import navigate_with_retry, is_error_page
from config import settings

logger = logging.getLogger(__name__)


def _jittered_sleep(base_seconds: float) -> None:
    """带随机扰动的等待（±20%），模拟人工操作节奏"""
    jitter = base_seconds * 0.2
    actual = base_seconds + random.uniform(-jitter, jitter)
    time.sleep(max(0.5, actual))


def _check_signal(task_id: Optional[str]) -> None:
    """检查任务控制信号，stop 信号会触发 StopSignal 异常"""
    if not task_id:
        return
    # 延迟导入避免循环引用
    import api.services.task_manager as _task_mgr
    from crawler.x_searcher import StopSignal

    while True:
        signal = _task_mgr.get_signal(task_id)
        if signal == "stop":
            raise StopSignal(f"回复抓取器收到终止信号: task_id={task_id}")
        elif signal == "pause":
            logger.info(f"回复抓取器已暂停 (task_id={task_id})，等待继续信号...")
            time.sleep(1)
        else:
            break


def fetch_replies(
    tweet_id: str,
    screen_name: str,
    max_count: int = 20,
    task_id: Optional[str] = None,
    timeout: Optional[float] = None,
    existing_tab=None,
) -> list[dict]:
    """
    抓取指定推文的所有回复。

    Args:
        tweet_id:     目标推文 ID
        screen_name:  发推用户的 screen_name（构建 URL 用）
        max_count:    最多获取回复数量（0 表示不限制）
        task_id:      爬取任务 ID（用于原始响应存储路径 + 信号检查）
        timeout:      等待数据包超时（秒），默认使用全局配置
        existing_tab: 复用已有标签页（不传则新开）

    Returns:
        回复 tweet dict 列表，每个 dict 带 thread_context 字段
    """
    if timeout is None:
        timeout = settings.crawler_timeout

    tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
    all_replies: list[dict] = []
    seen_ids: set[str] = set()
    page_num = 0

    # 决定是否使用外部传入的 tab（DFS 时复用避免频繁开关）
    tab = existing_tab if existing_tab else get_new_tab()
    should_close = (existing_tab is None)

    try:
        tab.listen.start(TWEET_DETAIL_PATTERN)
        logger.info(f"开始抓取回复: tweet_id={tweet_id}, url={tweet_url}")

        # 导航到推文详情页（含错误页自动刷新）
        ok = navigate_with_retry(
            tab,
            tweet_url,
            max_retries=3,
            base_wait=3.0,
            load_timeout=30.0,
            post_load_wait=settings.crawler_reply_wait,
            task_id=task_id,
        )
        if not ok:
            logger.error(f"推文详情页反复出现错误，跳过 tweet_id={tweet_id}")
            return []

        while True:
            # 每页检查控制信号
            _check_signal(task_id)

            page_num += 1
            logger.info(f"  等待回复第 {page_num} 页数据包（tweet_id={tweet_id}）...")
            packet = tab.listen.wait(timeout=timeout, raise_err=False)

            if not packet:
                # 超时时先检测是否出现了错误页
                if is_error_page(tab):
                    logger.warning(f"  回复第 {page_num} 页：检测到 X 错误页，尝试刷新...")
                    tab.listen.stop()
                    ok = navigate_with_retry(
                        tab, tweet_url,
                        max_retries=2, base_wait=3.0,
                        post_load_wait=settings.crawler_reply_wait,
                        task_id=task_id,
                    )
                    tab.listen.start(TWEET_DETAIL_PATTERN)
                    if ok:
                        logger.info(f"  回复第 {page_num} 页：刷新后恢复，重新等待数据包")
                        continue
                logger.warning(f"  回复第 {page_num} 页等待超时（tweet_id={tweet_id}）")
                break

            try:
                body = packet.response.body
                if not isinstance(body, dict):
                    logger.debug(f"  非 JSON 响应，跳过（url={packet.url[:80]}）")
                    continue

                # 持久化原始响应
                if task_id:
                    save_reply_response(task_id, tweet_id, page_num, body)

                _, page_replies, bottom_cursor, _ = parse_tweet_detail_response(
                    body, focal_tweet_id=tweet_id
                )

                # 去重
                new_replies = [r for r in page_replies if r.get("id") not in seen_ids]
                for r in new_replies:
                    seen_ids.add(r.get("id", ""))
                all_replies.extend(new_replies)

                logger.info(
                    f"  回复第 {page_num} 页：{len(page_replies)} 条（新增 {len(new_replies)} 条），"
                    f"累计 {len(all_replies)} 条（tweet_id={tweet_id}）"
                )

                # 达到上限
                if max_count and len(all_replies) >= max_count:
                    all_replies = all_replies[:max_count]
                    logger.info(f"  已达回复上限 {max_count} 条，停止")
                    break

                # 无更多评论
                if not bottom_cursor:
                    logger.info(f"  评论区无更多数据（tweet_id={tweet_id}）")
                    break

                # 滚动翻页前先等待（确保本页评论全部加载完毕）
                logger.info(f"  评论加载等待 {settings.crawler_reply_wait}s...")
                time.sleep(settings.crawler_reply_wait)

                # 滚动翻页（带随机扰动的间隔）
                _jittered_sleep(settings.crawler_page_interval)
                tab.scroll.to_bottom()

            except Exception as e:
                logger.error(f"  回复第 {page_num} 页解析失败: {e}", exc_info=True)
                break

    finally:
        tab.listen.stop()
        if should_close:
            try:
                tab.close()
            except Exception:
                pass

    logger.info(f"回复抓取完成: tweet_id={tweet_id}，共 {len(all_replies)} 条")
    return all_replies


def fetch_replies_batch(
    tweets: list[dict],
    max_replies_per_tweet: int = 20,
    task_id: Optional[str] = None,
    timeout: Optional[float] = None,
    progress_callback=None,
) -> list[dict]:
    """
    批量抓取多条推文的回复（BFS 广度优先模式下使用）。
    每条推文开独立标签页抓取，顺序执行。

    当收到 StopSignal 时，会将已抓取回复的推文 + 剩余未处理推文合并后
    通过 StopSignal.partial_tweets 携带，确保已抓取的回复数据不丢失。

    Args:
        tweets:                推文 dict 列表（需含 id 和 author.screen_name）
        max_replies_per_tweet: 每条推文最多抓取的回复数量
        task_id:               任务 ID
        timeout:               超时
        progress_callback:     每条推文完成后调用 callback(tweet_id, replies)

    Returns:
        将 replies 附加到原 tweets 上，返回更新后的列表
    """
    from crawler.x_searcher import StopSignal

    updated_tweets = []
    for i, tweet in enumerate(tweets):
        # 每条推文前检查信号
        try:
            _check_signal(task_id)
        except StopSignal as e:
            _merge_remaining_batch(updated_tweets, tweets, i)
            raise StopSignal(str(e), partial_tweets=updated_tweets)

        tweet_id = tweet.get("id", "")
        screen_name = (tweet.get("author") or {}).get("screen_name", "")

        if not tweet_id or not screen_name:
            logger.warning(f"推文缺少 id 或 screen_name，跳过回复抓取（index={i}）")
            updated_tweets.append(tweet)
            continue

        logger.info(f"[BFS] 抓取回复进度 {i+1}/{len(tweets)}: tweet_id={tweet_id}")
        try:
            replies = fetch_replies(
                tweet_id=tweet_id,
                screen_name=screen_name,
                max_count=max_replies_per_tweet,
                task_id=task_id,
                timeout=timeout,
            )
            tweet = dict(tweet)  # 浅拷贝，防止污染原对象
            tweet["replies"] = replies
        except StopSignal as e:
            # 当前推文的回复抓取被中断，标记空回复后携带已处理数据抛出
            tweet = dict(tweet)
            tweet["replies"] = []
            updated_tweets.append(tweet)
            _merge_remaining_batch(updated_tweets, tweets, i + 1)
            raise StopSignal(str(e), partial_tweets=updated_tweets)
        except Exception as e:
            logger.error(f"抓取 tweet_id={tweet_id} 回复失败: {e}", exc_info=True)
            tweet = dict(tweet)
            tweet["replies"] = []

        updated_tweets.append(tweet)

        if progress_callback:
            try:
                progress_callback(tweet_id, tweet.get("replies", []))
            except Exception:
                pass

        # 礼貌性间隔（带随机扰动），避免被封
        _jittered_sleep(settings.crawler_page_interval)

    return updated_tweets


def _merge_remaining_batch(updated: list[dict], tweets: list[dict], start_idx: int) -> None:
    """将未处理的推文（无 replies）追加到 updated 列表中"""
    for t in tweets[start_idx:]:
        t_copy = dict(t)
        t_copy.setdefault("replies", [])
        updated.append(t_copy)
