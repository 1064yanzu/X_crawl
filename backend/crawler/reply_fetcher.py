"""
回复抓取器模块（v3 - 支持 Show More 点击 + 渐进式滚动 + expected_count 参考）

变更：
- 翻页由简单滚动改为：滚动 + 检测并点击 "Show more replies" 按钮
- 使用推文元数据中的 reply_count 作为预期评论数参考
- 连续空页计数器防止无限循环
- 渐进式多步滚动确保懒加载内容完全触发
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

# "Show more replies" 按钮的文案（多语言兼容）
_SHOW_MORE_TEXTS = [
    "Show more replies",
    "Show additional replies",
    "显示更多回复",
    "显示其他回复",
    "もっと返信を表示",
    "Show",  # 兜底：部分场景下按钮只显示 "Show"
]

# 连续无新评论的最大重试次数（超过后认为评论区已到底）
_MAX_EMPTY_PAGES = 3


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


# ═══════════════════════════════════════════════════════════════════
#  翻页辅助函数
# ═══════════════════════════════════════════════════════════════════

def _click_show_more(tab) -> bool:
    """
    检测并点击 "Show more replies" / "显示更多回复" 等按钮。

    X 的推文详情页在评论区底部会放置这类按钮，点击后才会触发
    新的 TweetDetail API 请求加载更多评论。

    Returns:
        True 如果找到并成功点击了按钮，False 如果未找到
    """
    for text in _SHOW_MORE_TEXTS:
        try:
            # 使用 DrissionPage 的模糊文本匹配
            ele = tab.ele(f'text:{text}', timeout=2)
            if ele:
                # 先滚动到该元素可见位置
                ele.scroll.to_see()
                time.sleep(0.3)
                ele.click()
                logger.info(f"  ✅ 点击了 '{text}' 按钮")
                return True
        except Exception as e:
            logger.debug(f"  查找 '{text}' 按钮时异常: {e}")
            continue

    # 尝试通过 CSS 选择器查找（X 的 "Show more" 有时在特殊容器内）
    _CSS_SELECTORS = [
        # "Show more replies" 通常在 role=button 的 div 中
        'css:[role="button"] span',
        # cursor-type 按钮
        'css:[data-testid="cellInnerDiv"] [role="button"]',
    ]
    for selector in _CSS_SELECTORS:
        try:
            elements = tab.eles(selector, timeout=1)
            for ele in elements:
                ele_text = (ele.text or "").strip().lower()
                if any(keyword in ele_text for keyword in [
                    "show", "more", "replies",
                    "显示", "更多", "回复",
                ]):
                    ele.scroll.to_see()
                    time.sleep(0.3)
                    ele.click()
                    logger.info(f"  ✅ 通过 CSS 选择器点击了按钮（文本: '{ele_text}'）")
                    return True
        except Exception as e:
            logger.debug(f"  CSS 选择器 '{selector}' 查找异常: {e}")
            continue

    return False


def _scroll_incremental(tab, steps: int = 5, pause: float = 0.8) -> None:
    """
    渐进式多步滚动，模拟人工操作并确保触发所有懒加载。

    单次 scroll.to_bottom() 可能不足以触发 X 的懒加载评论，
    多次小步滚动可以更好地触发内容加载。

    Args:
        tab:    DrissionPage 标签页
        steps:  滚动步数
        pause:  每步之间的暂停时间（秒）
    """
    for i in range(steps):
        tab.scroll.down(500)  # 每次向下滚动 500px
        time.sleep(pause + random.uniform(-0.2, 0.3))
    # 最后滚到底部确保到达最底端
    tab.scroll.to_bottom()


def fetch_replies(
    tweet_id: str,
    screen_name: str,
    max_count: int = 20,
    task_id: Optional[str] = None,
    timeout: Optional[float] = None,
    existing_tab=None,
    expected_count: int = 0,
) -> tuple[list[dict], dict | None]:
    """
    抓取指定推文的所有回复。

    Args:
        tweet_id:       目标推文 ID
        screen_name:    发推用户的 screen_name（构建 URL 用）
        max_count:      最多获取回复数量（0 表示不限制）
        task_id:        爬取任务 ID（用于原始响应存储路径 + 信号检查）
        timeout:        等待数据包超时（秒），默认使用全局配置
        existing_tab:   复用已有标签页（不传则新开）
        expected_count: 推文元数据中的评论数（reply_count），作为参考

    Returns:
        (replies, failure_info) 元组：
        - replies: 回复 tweet dict 列表
        - failure_info: 失败/不全信息 dict（None 表示成功）
    """
    if timeout is None:
        timeout = settings.crawler_timeout

    tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
    all_replies: list[dict] = []
    seen_ids: set[str] = set()
    page_num = 0
    empty_page_count = 0  # 连续无新评论计数

    # 决定是否使用外部传入的 tab（DFS 时复用避免频繁开关）
    tab = existing_tab if existing_tab else get_new_tab()
    should_close = (existing_tab is None)

    # 日志中展示预期评论数以便对比
    expected_info = f"，预期约 {expected_count} 条" if expected_count else ""

    try:
        tab.listen.start(TWEET_DETAIL_PATTERN)
        logger.info(f"开始抓取回复: tweet_id={tweet_id}, url={tweet_url}{expected_info}")

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
            failure = {
                "tweet_id": tweet_id,
                "screen_name": screen_name,
                "expected_count": expected_count,
                "fetched_count": 0,
                "error_reason": "推文详情页反复加载失败",
            }
            return [], failure

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

                # 超时但还没抓够预期数量 → 再尝试一次点击/滚动
                if expected_count and len(all_replies) < expected_count * 0.5:
                    logger.info(
                        f"  超时但仅抓到 {len(all_replies)}/{expected_count} 条，"
                        f"尝试点击加载更多..."
                    )
                    clicked = _click_show_more(tab)
                    if clicked:
                        time.sleep(settings.crawler_reply_wait)
                        continue
                    # 点击失败，渐进式滚动再试一次
                    _scroll_incremental(tab)
                    time.sleep(settings.crawler_reply_wait)
                    # 给最后一次机会
                    packet = tab.listen.wait(timeout=timeout / 2, raise_err=False)
                    if packet:
                        # 拿到了数据包，跳到下方解析逻辑处理
                        pass
                    else:
                        logger.warning(f"  回复第 {page_num} 页等待超时（tweet_id={tweet_id}）")
                        break
                else:
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
                    f"  回复第 {page_num} 页：{len(page_replies)} 条"
                    f"（新增 {len(new_replies)} 条），"
                    f"累计 {len(all_replies)} 条"
                    f"{'/' + str(expected_count) if expected_count else ''}"
                    f"（tweet_id={tweet_id}）"
                )

                # 更新连续空页计数
                if len(new_replies) == 0:
                    empty_page_count += 1
                    if empty_page_count >= _MAX_EMPTY_PAGES:
                        logger.info(
                            f"  连续 {_MAX_EMPTY_PAGES} 页无新评论，停止翻页"
                        )
                        break
                else:
                    empty_page_count = 0  # 有新数据则重置计数

                # 达到上限
                if max_count and len(all_replies) >= max_count:
                    all_replies = all_replies[:max_count]
                    logger.info(f"  已达回复上限 {max_count} 条，停止")
                    break

                # 无更多评论（API 没有返回 bottom_cursor）
                if not bottom_cursor:
                    # 如果预期还有更多评论，尝试通过点击按钮加载
                    if expected_count and len(all_replies) < expected_count * 0.5:
                        logger.info(
                            f"  API 无 cursor 但仅抓到 {len(all_replies)}/{expected_count} 条，"
                            f"尝试点击按钮加载更多..."
                        )
                        clicked = _click_show_more(tab)
                        if clicked:
                            time.sleep(settings.crawler_reply_wait)
                            continue
                    logger.info(f"  评论区无更多数据（tweet_id={tweet_id}）")
                    break

                # ── 翻页操作：按钮点击 + 滚动 ──────────────────────

                # 先等待确保本页评论 DOM 渲染完毕
                logger.info(f"  评论加载等待 {settings.crawler_reply_wait}s...")
                time.sleep(settings.crawler_reply_wait)

                # 随机扰动间隔
                _jittered_sleep(settings.crawler_page_interval)

                # 方案1：优先尝试点击 "Show more replies" 按钮
                clicked = _click_show_more(tab)
                if clicked:
                    # 点击成功后等待数据加载
                    time.sleep(settings.crawler_reply_wait)
                else:
                    # 方案2：按钮不存在，使用渐进式滚动触发懒加载
                    logger.info(f"  未找到加载更多按钮，使用渐进式滚动...")
                    _scroll_incremental(tab)
                    time.sleep(settings.crawler_reply_wait)

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

    # 输出抓取结果摘要
    coverage = ""
    if expected_count:
        pct = round(len(all_replies) / expected_count * 100) if expected_count else 0
        coverage = f"（覆盖率 {pct}%，预期 {expected_count} 条）"
    logger.info(f"回复抓取完成: tweet_id={tweet_id}，共 {len(all_replies)} 条{coverage}")

    # 判定是否需要记录为失败/不全
    failure_info = None
    if expected_count and expected_count > 0:
        pct = len(all_replies) / expected_count * 100 if expected_count else 100
        if pct < 50 and expected_count >= 3:
            failure_info = {
                "tweet_id": tweet_id,
                "screen_name": screen_name,
                "expected_count": expected_count,
                "fetched_count": len(all_replies),
                "error_reason": f"覆盖率不足 ({pct:.0f}%)，预期 {expected_count} 条仅抓到 {len(all_replies)} 条",
            }
    if len(all_replies) == 0 and expected_count and expected_count > 0:
        if not failure_info:
            failure_info = {
                "tweet_id": tweet_id,
                "screen_name": screen_name,
                "expected_count": expected_count,
                "fetched_count": 0,
                "error_reason": "未抓取到任何评论",
            }

    return all_replies, failure_info


def fetch_replies_batch(
    tweets: list[dict],
    max_replies_per_tweet: int = 20,
    task_id: Optional[str] = None,
    timeout: Optional[float] = None,
    progress_callback=None,
) -> tuple[list[dict], list[dict]]:
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
        (updated_tweets, failed_records) 元组
    """
    from crawler.x_searcher import StopSignal

    updated_tweets = []
    failed_records: list[dict] = []

    for i, tweet in enumerate(tweets):
        # 每条推文前检查信号
        try:
            _check_signal(task_id)
        except StopSignal as e:
            _merge_remaining_batch(updated_tweets, tweets, i)
            raise StopSignal(str(e), partial_tweets=updated_tweets)

        tweet_id = tweet.get("id", "")
        screen_name = (tweet.get("author") or {}).get("screen_name", "")
        # 从推文元数据获取预期评论数
        expected_count = (tweet.get("metrics") or {}).get("replies", 0)

        if not tweet_id or not screen_name:
            logger.warning(f"推文缺少 id 或 screen_name，跳过回复抓取（index={i}）")
            updated_tweets.append(tweet)
            continue

        # 跳过 0 评论的帖子，无需打开详情页
        if expected_count == 0:
            logger.info(
                f"[BFS] 跳过 tweet_id={tweet_id}（0 条评论），无需抓取回复"
            )
            tweet = dict(tweet)
            tweet["replies"] = []
            updated_tweets.append(tweet)
            if progress_callback:
                try:
                    progress_callback(tweet_id, [])
                except Exception:
                    pass
            continue

        logger.info(
            f"[BFS] 抓取回复进度 {i+1}/{len(tweets)}: "
            f"tweet_id={tweet_id}，预期评论 {expected_count} 条"
        )
        try:
            replies, failure_info = fetch_replies(
                tweet_id=tweet_id,
                screen_name=screen_name,
                max_count=max_replies_per_tweet,
                task_id=task_id,
                timeout=timeout,
                expected_count=expected_count,
            )
            tweet = dict(tweet)  # 浅拷贝，防止污染原对象
            tweet["replies"] = replies
            if failure_info:
                failure_info["task_id"] = task_id or ""
                failed_records.append(failure_info)
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
            failed_records.append({
                "task_id": task_id or "",
                "tweet_id": tweet_id,
                "screen_name": screen_name,
                "expected_count": expected_count,
                "fetched_count": 0,
                "error_reason": f"异常: {str(e)[:200]}",
            })

        updated_tweets.append(tweet)

        if progress_callback:
            try:
                progress_callback(tweet_id, tweet.get("replies", []))
            except Exception:
                pass

        # 礼貌性间隔（带随机扰动），避免被封
        _jittered_sleep(settings.crawler_page_interval)

    return updated_tweets, failed_records


def _merge_remaining_batch(updated: list[dict], tweets: list[dict], start_idx: int) -> None:
    """将未处理的推文（无 replies）追加到 updated 列表中"""
    for t in tweets[start_idx:]:
        t_copy = dict(t)
        t_copy.setdefault("replies", [])
        updated.append(t_copy)
