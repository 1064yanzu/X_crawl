"""
回复抓取器模块（v5 - 纯滚动翻页 + expected_count 参考）

变更（v5）：
- 根据抓包分析，确认 X 评论区翻页是纯滚动触发 TweetDetail API，无 "Show more" 按钮
- 删除 _click_show_more 及相关逻辑，简化翻页为：滚动 → 等待数据包 → 解析
- 保留渐进式多步滚动确保懒加载内容完全触发
- 保留快速退出、连续空页计数器、随机扰动等策略
"""
import time
import random
import logging
from typing import Optional

from crawler.browser import get_new_tab
from crawler.reply_parser import parse_tweet_detail_response, TWEET_DETAIL_PATTERN
from crawler.response_saver import save_reply_response
from crawler.page_health import navigate_with_retry
from crawler.page_state import detect_page_state, PageState
from crawler.packet_guard import wait_for_target_packet, is_tweet_detail_body
from crawler.recovery_policy import RecoveryPolicy, soft_recover_for_packet, backoff_seconds, sleep_with_jitter
from crawler.crawl_signals import StopSignal, ChallengeSignal, RiskState
from crawler.utils import jittered_sleep, check_signal, merge_remaining, interruptible_sleep
from crawler.runtime_metrics import bump_metric
from config import settings

logger = logging.getLogger(__name__)

# 连续无新评论的最大重试次数（超过后认为评论区已到底）
_MAX_EMPTY_PAGES = 3


def _to_risk_state(state: PageState) -> RiskState:
    if state == PageState.RATE_LIMITED:
        return "rate_limited"
    if state == PageState.LOGIN_REQUIRED:
        return "login_required"
    return "challenge"


# ═══════════════════════════════════════════════════════════════════
#  翻页辅助函数
# ═══════════════════════════════════════════════════════════════════


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


def _wait_reply_packet_with_recovery(
    *,
    tab,
    timeout: float,
    page_num: int,
    tweet_url: str,
    task_id: Optional[str],
    policy: RecoveryPolicy,
):
    """等待 TweetDetail 数据包，超时时执行软恢复与硬刷新。"""
    risk_hits = 0

    for soft_attempt in range(policy.packet_soft_retries + 1):
        packet, ignored = wait_for_target_packet(
            tab,
            timeout=timeout,
            accept_body=is_tweet_detail_body,
        )
        if packet:
            if ignored:
                logger.debug(f"  回复第 {page_num} 页过滤无关包 {ignored} 个")
            return packet
        bump_metric(task_id, "reply_packet_timeouts")

        state, reason = detect_page_state(tab)
        if state in {PageState.CHALLENGE, PageState.RATE_LIMITED, PageState.LOGIN_REQUIRED}:
            risk_hits += 1
            bump_metric(task_id, "risk_hits")
            if risk_hits > policy.challenge_retry_times:
                raise ChallengeSignal(
                    f"回复页检测到 {state.value} 且重试耗尽：{reason}",
                    risk_state=_to_risk_state(state),
                )
            logger.warning(
                f"  回复第 {page_num} 页风险状态 state={state.value}，"
                f"冷却后重试（{risk_hits}/{policy.challenge_retry_times}）"
            )
            sleep_with_jitter(policy.challenge_cooldown, jitter_ratio=0.1, minimum=0.8)

        if soft_attempt < policy.packet_soft_retries:
            bump_metric(task_id, "soft_retries")
            soft_recover_for_packet(tab, soft_attempt)
            continue

    for hard_attempt in range(policy.refresh_max_retries):
        bump_metric(task_id, "hard_refreshes")
        wait = backoff_seconds(hard_attempt, base=2.0, cap=35.0)
        logger.warning(
            f"  回复第 {page_num} 页硬恢复刷新 {hard_attempt + 1}/{policy.refresh_max_retries}，"
            f"退避 {wait:.1f}s"
        )
        sleep_with_jitter(wait, jitter_ratio=0.2, minimum=0.6)
        tab.listen.stop()
        ok = navigate_with_retry(
            tab,
            tweet_url,
            max_retries=1,
            base_wait=2.5,
            post_load_wait=settings.crawler_reply_wait,
            challenge_retry_times=policy.challenge_retry_times,
            challenge_cooldown=policy.challenge_cooldown,
            raise_on_risk=True,
            task_id=task_id,
        )
        tab.listen.start(TWEET_DETAIL_PATTERN)
        if not ok:
            continue

        packet, _ = wait_for_target_packet(
            tab,
            timeout=timeout,
            accept_body=is_tweet_detail_body,
        )
        if packet:
            return packet

    return None


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
    policy = RecoveryPolicy.from_settings(settings)

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
            max_retries=policy.refresh_max_retries,
            base_wait=3.0,
            load_timeout=30.0,
            post_load_wait=settings.crawler_reply_wait,
            challenge_retry_times=policy.challenge_retry_times,
            challenge_cooldown=policy.challenge_cooldown,
            raise_on_risk=True,
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
            check_signal(task_id)

            page_num += 1
            logger.info(f"  等待回复第 {page_num} 页数据包（tweet_id={tweet_id}）...")
            packet = _wait_reply_packet_with_recovery(
                tab=tab,
                timeout=timeout,
                page_num=page_num,
                tweet_url=tweet_url,
                task_id=task_id,
                policy=policy,
            )

            if not packet:
                # 恢复失败但覆盖率不足时，尝试额外滚动触发加载
                if expected_count and len(all_replies) < expected_count * 0.5:
                    logger.info(
                        f"  恢复后仍未抓到数据（{len(all_replies)}/{expected_count}），"
                        f"尝试额外滚动触发加载..."
                    )
                    _scroll_incremental(tab)
                    interruptible_sleep(settings.crawler_reply_wait, task_id=task_id)
                    packet, _ = wait_for_target_packet(
                        tab,
                        timeout=max(5.0, timeout / 2),
                        accept_body=is_tweet_detail_body,
                    )
                    if not packet:
                        logger.warning(f"  回复第 {page_num} 页连续超时（tweet_id={tweet_id}）")
                        break
                else:
                    logger.warning(f"  回复第 {page_num} 页连续超时（tweet_id={tweet_id}）")
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
                    bump_metric(task_id, "empty_pages")
                    if empty_page_count >= _MAX_EMPTY_PAGES:
                        logger.info(
                            f"  连续 {_MAX_EMPTY_PAGES} 页无新评论，停止翻页"
                        )
                        break
                else:
                    empty_page_count = 0  # 有新数据则重置计数

                # ── 快速退出：评论数较少的帖子第一页即可完成 ────────
                if page_num == 1 and expected_count > 0:
                    # 条件1：已获取评论数已达到或超过预期数量
                    if len(all_replies) >= expected_count:
                        logger.info(
                            f"  ✅ 快速完成：第一页已获取 {len(all_replies)} 条评论"
                            f"（预期 {expected_count} 条），无需翻页"
                        )
                        break
                    # 条件2：API 无分页游标 + 覆盖率 ≥ 80%（reply_count 可能不完全准确）
                    if not bottom_cursor and len(all_replies) >= expected_count * 0.8:
                        pct = len(all_replies) / expected_count * 100
                        logger.info(
                            f"  ✅ 快速完成：无更多分页且已达 {len(all_replies)}/{expected_count} "
                            f"条（覆盖率 {pct:.0f}%），跳过翻页"
                        )
                        break


                if max_count and len(all_replies) >= max_count:
                    all_replies = all_replies[:max_count]
                    logger.info(f"  已达回复上限 {max_count} 条，停止")
                    break

                # 无更多评论（API 没有返回 bottom_cursor）
                if not bottom_cursor:
                    if expected_count and len(all_replies) < expected_count * 0.5:
                        # 覆盖率不足但 API 没给 cursor，尝试额外滚动
                        logger.info(
                            f"  API 无 cursor 但仅抓到 {len(all_replies)}/{expected_count} 条，"
                            f"尝试额外滚动触发加载..."
                        )
                        _scroll_incremental(tab)
                        interruptible_sleep(settings.crawler_reply_wait, task_id=task_id)
                        continue
                    logger.info(f"  评论区无更多数据（tweet_id={tweet_id}）")
                    break

                # ── 翻页操作：渐进式滚动触发懒加载 ──────────────────────

                # 先等待确保本页评论 DOM 渲染完毕
                logger.debug(f"  评论加载等待 {settings.crawler_reply_wait}s...")
                interruptible_sleep(settings.crawler_reply_wait, task_id=task_id)

                # 随机扰动间隔
                jittered_sleep(settings.crawler_page_interval, task_id=task_id)

                # 渐进式滚动到底部，触发 TweetDetail API 加载更多评论
                logger.debug(f"  执行渐进式滚动加载下一页评论...")
                _scroll_incremental(tab)
                interruptible_sleep(settings.crawler_reply_wait, task_id=task_id)

            except ChallengeSignal:
                raise
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
    strategy: str = "bfs",
    reply_depth: int = 2,
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
    import api.services.task_manager as _task_mgr

    tag = strategy.upper()  # "BFS" 或 "DFS"，用于日志
    updated_tweets = []
    failed_records: list[dict] = []

    for i, tweet in enumerate(tweets):
        # 每条推文前检查信号
        try:
            check_signal(task_id)
        except StopSignal as e:
            merge_remaining(updated_tweets, tweets, i)
            raise StopSignal(str(e), partial_tweets=updated_tweets)

        tweet_id = tweet.get("id", "")
        screen_name = (tweet.get("author") or {}).get("screen_name", "")
        # 从推文元数据获取预期评论数
        expected_count = (tweet.get("metrics") or {}).get("replies", 0)

        if not tweet_id or not screen_name:
            logger.warning(f"推文缺少 id 或 screen_name，跳过回复抓取（index={i}）")
            updated_tweets.append(tweet)
            continue

        # 跳过已有回复数据的推文（断点恢复时避免重复抓取）
        existing_replies = tweet.get("replies")
        if existing_replies is not None:
            logger.info(
                f"[{tag}] 跳过 tweet_id={tweet_id}（已有 {len(existing_replies)} 条回复），"
                f"无需重复抓取"
            )
            updated_tweets.append(tweet)
            if progress_callback:
                try:
                    progress_callback(tweet_id, existing_replies)
                except Exception:
                    pass
            continue

        # 跳过 0 评论的帖子，无需打开详情页
        if expected_count == 0:
            logger.info(
                f"[{tag}] 跳过 tweet_id={tweet_id}（0 条评论），无需抓取回复"
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

        # 更新阶段提示（告知用户正在抓第几条推文的回复）
        if task_id:
            _task_mgr.update_task_phase(
                task_id,
                f"[{tag}] 正在抓取第 {i + 1}/{len(tweets)} 条推文的回复 "
                f"(@{screen_name}，预期 {expected_count} 条)..."
            )

        logger.info(
            f"[{tag}] 抓取回复进度 {i+1}/{len(tweets)}: "
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

            # ── 二级评论递归抓取 ───────────────────────────────
            if replies and reply_depth > 1:
                from crawler.nested_reply_fetcher import fetch_nested_replies
                try:
                    tweet["replies"], nested_failed = fetch_nested_replies(
                        replies,
                        current_depth=1,
                        max_depth=reply_depth,
                        max_replies_per_tweet=max_replies_per_tweet,
                        task_id=task_id,
                        timeout=timeout,
                    )
                    failed_records.extend(nested_failed)
                except StopSignal as e:
                    updated_tweets.append(tweet)
                    merge_remaining(updated_tweets, tweets, i + 1)
                    raise StopSignal(str(e), partial_tweets=updated_tweets)
                except ChallengeSignal:
                    raise
                except Exception as e:
                    logger.error(f"拓展抓取 tweet_id={tweet_id} 的子评论失败: {e}", exc_info=True)
        except StopSignal as e:
            # 当前推文的回复抓取被中断，标记空回复后携带已处理数据抛出
            tweet = dict(tweet)
            tweet["replies"] = []
            updated_tweets.append(tweet)
            merge_remaining(updated_tweets, tweets, i + 1)
            raise StopSignal(str(e), partial_tweets=updated_tweets)
        except ChallengeSignal:
            raise
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
        jittered_sleep(settings.crawler_page_interval, task_id=task_id)

    return updated_tweets, failed_records
