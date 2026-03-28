"""
回复抓取器模块（v5 - 纯滚动翻页 + expected_count 参考）

变更（v5）：
- 根据抓包分析，确认 X 评论区翻页是纯滚动触发 TweetDetail API，无 "Show more" 按钮
- 删除 _click_show_more 及相关逻辑，简化翻页为：滚动 → 等待数据包 → 解析
- 保留渐进式多步滚动确保懒加载内容完全触发
- 保留快速退出、连续空页计数器、随机扰动等策略
"""
import logging
import random
import time
from typing import Optional

from crawler.browser import get_new_tab, promote_browser_for_manual_interaction
from crawler.reply_parser import parse_tweet_detail_response, TWEET_DETAIL_PATTERN
from crawler.response_saver import save_reply_response
from crawler.page_health import navigate_with_retry
from crawler.page_state import detect_page_state, PageState
from crawler.packet_guard import wait_for_target_packet, is_tweet_detail_body, extract_packet_body_dict
from crawler.recovery_policy import RecoveryPolicy, soft_recover_for_packet, backoff_seconds, sleep_with_jitter
from crawler.crawl_signals import StopSignal, ChallengeSignal, RiskState
from crawler.utils import jittered_sleep, check_signal, merge_remaining, interruptible_sleep
from crawler.scroll_safe import safe_scroll_down, safe_scroll_up, safe_scroll_to_bottom
from crawler.runtime_metrics import bump_metric
from crawler.rate_tracker import get_tracker, extract_rate_headers
from crawler import telemetry
from crawler.wait_policy import (
    quick_probe_timeout,
    compensation_probe_timeout,
    before_scroll_wait,
    scroll_steps,
    scroll_step_pause,
)
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


def _scroll_incremental(tab, *, task_id: Optional[str] = None, steps: Optional[int] = None) -> None:
    """
    评论区渐进式滚动：模拟人类浏览评论列表。

    轻量版：2~4 步，保持随机特征即可，避免占用过多时间。
    """
    move_steps = steps if steps is not None else random.randint(2, 4)
    for i in range(move_steps):
        # 小幅随机滚动（一条评论约 150~300px 高）
        px = random.randint(150, 350)
        safe_scroll_down(tab, px, task_id=task_id)

        # 阅读评论的停顿：大部分快速过，偶尔停一下
        if random.random() < 0.12:
            interruptible_sleep(random.uniform(0.8, 1.5), task_id=task_id)
        else:
            scroll_step_pause(task_id=task_id)

        # 偶尔回滚看上面的评论（非最后一步）
        if i < move_steps - 1 and random.random() < 0.08:
            safe_scroll_up(tab, random.randint(50, 120), task_id=task_id)
            interruptible_sleep(random.uniform(0.2, 0.4), task_id=task_id)

    # 最后滚到底部确保触发评论懒加载
    safe_scroll_to_bottom(tab, task_id=task_id)


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
    probe_timeout = quick_probe_timeout(timeout)
    packet, ignored = wait_for_target_packet(
        tab,
        timeout=probe_timeout,
        accept_body=is_tweet_detail_body,
    )
    if packet:
        if ignored:
            logger.debug(f"  回复第 {page_num} 页快速探测过滤无关包 {ignored} 个")
        _update_reply_rate_tracker(packet, task_id=task_id)
        return packet

    for soft_attempt in range(policy.packet_soft_retries + 1):
        packet, ignored = wait_for_target_packet(
            tab,
            timeout=compensation_probe_timeout(timeout),
            accept_body=is_tweet_detail_body,
        )
        if packet:
            if ignored:
                logger.debug(f"  回复第 {page_num} 页过滤无关包 {ignored} 个")
            _update_reply_rate_tracker(packet, task_id=task_id)
            return packet
        bump_metric(task_id, "reply_packet_timeouts")

        state, reason = detect_page_state(tab)
        if state in {PageState.CHALLENGE, PageState.RATE_LIMITED, PageState.LOGIN_REQUIRED}:
            risk_hits += 1
            bump_metric(task_id, "risk_hits")
            telemetry.record_event(
                task_id,
                "reply_risk_detected",
                status="running",
                phase=f"回复页检测到风险状态 {state.value}",
                page=page_num,
                risk_state=_to_risk_state(state),
                meta={"tweet_url": tweet_url, "hit": risk_hits},
            )
            # 首次就提醒用户在浏览器中完成验证
            if risk_hits == 1:
                promote_browser_for_manual_interaction(tab, reason=state.value)
            if risk_hits > policy.challenge_retry_times:
                promote_browser_for_manual_interaction(tab, reason=state.value)
                raise ChallengeSignal(
                    f"回复页检测到 {state.value} 且重试耗尽：{reason}",
                    risk_state=_to_risk_state(state),
                )
            logger.warning(
                f"  回复第 {page_num} 页风险状态 state={state.value}，"
                f"等待用户完成验证（{risk_hits}/{policy.challenge_retry_times}）"
            )
            sleep_with_jitter(policy.challenge_cooldown, jitter_ratio=0.1, minimum=0.8)
            # 冷却后重新检测（不刷新，等用户手动完成验证）
            recheck_state, _ = detect_page_state(tab)
            if recheck_state == PageState.OK:
                logger.info(f"  回复第 {page_num} 页用户已完成验证，页面恢复正常")
                continue

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
        try:
            tab.listen.stop()
        except Exception:
            pass
        tab.listen.start(TWEET_DETAIL_PATTERN)
        ok = navigate_with_retry(
            tab,
            tweet_url,
            max_retries=1,
            base_wait=2.5,
            post_load_wait=min(1.5, settings.crawler_reply_wait * 0.4),
            challenge_retry_times=policy.challenge_retry_times,
            challenge_cooldown=policy.challenge_cooldown,
            raise_on_risk=True,
            task_id=task_id,
        )
        if not ok:
            continue

        packet, _ = wait_for_target_packet(
            tab,
            timeout=compensation_probe_timeout(timeout),
            accept_body=is_tweet_detail_body,
        )
        if packet:
            _update_reply_rate_tracker(packet, task_id=task_id)
            return packet

    return None


def _update_reply_rate_tracker(packet, *, task_id: Optional[str] = None) -> None:
    """从 TweetDetail 数据包提取速率限制头并更新 tracker。"""
    result = extract_rate_headers(packet)
    if result:
        ep, remaining, limit, reset_ts = result
        get_tracker().update(ep, remaining, limit, reset_ts, task_id=task_id)


def _get_rate_limit_wait_sec(endpoint: str = "tweet_detail") -> float:
    """
    估算当前账号距限速重置的等待时间（秒）。
    从 rate_tracker 中读取最近一次响应头记录的 reset_ts。
    若无记录或已过期，返回保守估计 900s（15分钟）。
    """
    reset_ts = get_tracker().get_reset_ts(endpoint)
    if reset_ts > 0:
        wait = reset_ts - time.time()
        if 0 < wait < 1800:  # 合理范围：0~30 分钟
            return wait
    return 900.0  # 保守估计


def _pick_replacement_account(frozen_id: str, pool) -> "AccountEntry | None":
    """从池中选出一个不同于冻结账号的可用账号（round-robin 中第一个可用的）。"""
    return pool.pick_next_account(frozen_id)


def fetch_replies(
    tweet_id: str,
    screen_name: str,
    max_count: int = 20,
    task_id: Optional[str] = None,
    timeout: Optional[float] = None,
    existing_tab=None,
    expected_count: int = 0,
    browser_instance=None,
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
    if existing_tab is not None:
        tab = existing_tab
    elif browser_instance is not None:
        tab = browser_instance.new_tab()
    else:
        tab = get_new_tab()
    should_close = (existing_tab is None)

    # 日志中展示预期评论数以便对比
    expected_info = f"，预期约 {expected_count} 条" if expected_count else ""

    try:
        tab.listen.start(TWEET_DETAIL_PATTERN)
        logger.info(f"开始抓取回复: tweet_id={tweet_id}, url={tweet_url}{expected_info}")
        telemetry.record_event(
            task_id,
            "reply_fetch_started",
            status="running",
            phase=f"开始抓取回复 tweet_id={tweet_id}",
            meta={"tweet_id": tweet_id, "screen_name": screen_name, "expected_count": expected_count},
        )

        # 导航到推文详情页（含错误页自动刷新）
        ok = navigate_with_retry(
            tab,
            tweet_url,
            max_retries=policy.refresh_max_retries,
            base_wait=3.0,
            load_timeout=30.0,
            post_load_wait=min(1.5, settings.crawler_reply_wait * 0.4),
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
            telemetry.record_event(
                task_id,
                "reply_wait_packet",
                status="running",
                phase=f"等待回复第 {page_num} 页数据包",
                page=page_num,
                meta={"tweet_id": tweet_id},
            )
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
                    _scroll_incremental(tab, task_id=task_id)
                    packet, _ = wait_for_target_packet(
                        tab,
                        timeout=compensation_probe_timeout(timeout),
                        accept_body=is_tweet_detail_body,
                    )
                    if not packet:
                        logger.warning(f"  回复第 {page_num} 页连续超时（tweet_id={tweet_id}）")
                        telemetry.record_event(
                            task_id,
                            "reply_packet_timeout_stop",
                            status="running",
                            phase=f"回复第 {page_num} 页连续超时，停止当前推文回复抓取",
                            page=page_num,
                            meta={"tweet_id": tweet_id},
                        )
                        break
                else:
                    logger.warning(f"  回复第 {page_num} 页连续超时（tweet_id={tweet_id}）")
                    telemetry.record_event(
                        task_id,
                        "reply_packet_timeout_stop",
                        status="running",
                        phase=f"回复第 {page_num} 页连续超时，停止当前推文回复抓取",
                        page=page_num,
                        meta={"tweet_id": tweet_id},
                    )
                    break

            try:
                body = extract_packet_body_dict(packet)
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
                telemetry.record_event(
                    task_id,
                    "reply_page_parsed",
                    status="running",
                    phase=f"回复第 {page_num} 页解析完成",
                    page=page_num,
                    delta_replies=len(new_replies),
                    meta={"tweet_id": tweet_id, "total_replies": len(all_replies)},
                )

                # 更新连续空页计数
                if len(new_replies) == 0:
                    empty_page_count += 1
                    # 低评论推文快速放弃：预期 ≤3 条但首页就没数据，不值得重试
                    if expected_count > 0 and expected_count <= 3 and page_num == 1:
                        logger.info(
                            f"  低评论推文首页无数据（预期 {expected_count} 条），直接跳过"
                        )
                        break
                    bump_metric(task_id, "empty_pages")
                    if empty_page_count >= _MAX_EMPTY_PAGES:
                        logger.info(
                            f"  连续 {_MAX_EMPTY_PAGES} 页无新评论，停止翻页"
                        )
                        break
                else:
                    empty_page_count = 0  # 有新数据则重置计数

                # ── 快速退出：评论数已达标时立即完成 ────────
                if expected_count > 0:
                    # 条件1：已获取评论数已达到或超过预期数量
                    if len(all_replies) >= expected_count:
                        logger.info(
                            f"  ✅ 快速完成：已获取 {len(all_replies)} 条评论"
                            f"（预期 {expected_count} 条），无需翻页"
                        )
                        telemetry.record_event(
                            task_id,
                            "reply_quick_complete",
                            status="running",
                            phase="回复已达到预期，快速完成",
                            page=page_num,
                            meta={"tweet_id": tweet_id, "fetched": len(all_replies), "expected": expected_count},
                        )
                        break
                    # 条件2：API 无分页游标 + 覆盖率 ≥ 80%（reply_count 可能不完全准确）
                    if not bottom_cursor and len(all_replies) >= expected_count * 0.8:
                        pct = len(all_replies) / expected_count * 100
                        logger.info(
                            f"  ✅ 快速完成：无更多分页且已达 {len(all_replies)}/{expected_count} "
                            f"条（覆盖率 {pct:.0f}%），跳过翻页"
                        )
                        telemetry.record_event(
                            task_id,
                            "reply_quick_complete",
                            status="running",
                            phase="回复覆盖率达标且无更多分页，快速完成",
                            page=page_num,
                            meta={"tweet_id": tweet_id, "fetched": len(all_replies), "expected": expected_count},
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
                        _scroll_incremental(tab, task_id=task_id)
                        continue
                    logger.info(f"  评论区无更多数据（tweet_id={tweet_id}）")
                    break

                # ── 翻页操作：渐进式滚动触发懒加载 ──────────────────────
                before_scroll_wait(task_id=task_id)

                # 渐进式滚动到底部，触发 TweetDetail API 加载更多评论
                logger.debug(f"  执行渐进式滚动加载下一页评论...")
                _scroll_incremental(tab, task_id=task_id)

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
    telemetry.record_event(
        task_id,
        "reply_fetch_finished",
        status="running",
        phase=f"回复抓取完成 tweet_id={tweet_id}",
        delta_replies=len(all_replies),
        meta={"tweet_id": tweet_id, "coverage": coverage},
    )

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
    strategy: str = "dfs",
    reply_depth: int = 2,
    browser_instance=None,
) -> tuple[list[dict], list[dict]]:
    """
    批量抓取多条推文的回复（统一 DFS 模式，搜到即抓）。
    每条推文开独立标签页抓取，顺序执行。
    支持跨任务去重：互动指标未变化的推文直接复用缓存评论。

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
    from config import settings as _settings
    from crawler.tweet_dedup import check_dedup, register_tweets

    tag = strategy.upper()
    dedup_enabled = _settings.crawler_dedup_enabled
    dedup_hit_count = 0
    updated_tweets = []
    failed_records: list[dict] = []

    # ── 创建 batch 级共享 tab（避免每条推文都开关 tab） ──────────────
    _shared_reply_tab = None
    _owns_shared_tab = False
    if browser_instance is not None:
        _shared_reply_tab = browser_instance.new_tab()
        _owns_shared_tab = True
    elif reply_depth <= 1:
        # 非嵌套模式：batch 内共享同一个 tab
        _shared_reply_tab = get_new_tab()
        _owns_shared_tab = True

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

        # ── 跨任务去重检查（缓存命中跳过评论抓取） ─────────────
        if dedup_enabled:
            hit, cached_replies = check_dedup(tweet)
            if hit and cached_replies is not None:
                dedup_hit_count += 1
                tweet = dict(tweet)
                tweet["replies"] = cached_replies
                updated_tweets.append(tweet)
                logger.info(
                    f"[{tag}] 去重命中 tweet_id={tweet_id}，"
                    f"复用 {len(cached_replies)} 条缓存评论"
                )
                telemetry.record_event(
                    task_id,
                    "reply_dedup_hit",
                    status="running",
                    phase=f"[{tag}] 推文命中去重缓存",
                    delta_replies=len(cached_replies),
                    meta={"tweet_id": tweet_id},
                )
                if progress_callback:
                    try:
                        progress_callback(tweet_id, cached_replies)
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
        # 当需要抓二级评论时，手动开标签页让一级评论页面保持打开
        # 模拟人类行为：打开推文→看评论→点击评论看子评论→全看完再关闭
        need_nested = (reply_depth > 1)
        if need_nested:
            reply_tab = browser_instance.new_tab() if browser_instance is not None else get_new_tab()
        else:
            reply_tab = _shared_reply_tab  # 复用 batch 级共享 tab

        try:
            replies, failure_info = fetch_replies(
                tweet_id=tweet_id,
                screen_name=screen_name,
                max_count=max_replies_per_tweet,
                task_id=task_id,
                timeout=timeout,
                expected_count=expected_count,
                existing_tab=reply_tab,  # 传入外部 tab，fetch_replies 不会关闭它
                browser_instance=browser_instance,
            )
            tweet = dict(tweet)  # 浅拷贝，防止污染原对象
            tweet["replies"] = replies
            if failure_info:
                failure_info["task_id"] = task_id or ""
                failed_records.append(failure_info)

            # ── 二级评论递归抓取（一级评论标签页保持打开） ─────────
            if replies and need_nested:
                from crawler.nested_reply_fetcher import fetch_nested_replies
                try:
                    tweet["replies"], nested_failed = fetch_nested_replies(
                        replies,
                        current_depth=1,
                        max_depth=reply_depth,
                        max_replies_per_tweet=max_replies_per_tweet,
                        task_id=task_id,
                        timeout=timeout,
                        browser_instance=browser_instance,
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
            import traceback
            error_msg = str(e).lower()
            if "disconnected" in error_msg or "connection lost" in error_msg or "target closed" in error_msg:
                logger.warning(f"检测到浏览器断开连接，尝试恢复浏览器: {e}")
                from crawler.browser import ensure_browser_alive
                ensure_browser_alive()
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
        finally:
            # 二级评论全部抓完后，关闭一级评论标签页（仅嵌套模式独立 tab）
            if reply_tab and need_nested:
                try:
                    reply_tab.close()
                except Exception:
                    pass

        updated_tweets.append(tweet)

        if progress_callback:
            try:
                progress_callback(tweet_id, tweet.get("replies", []))
            except Exception:
                pass

        # 礼貌性间隔：基于 tweet_detail 动态间隔，多账号时自动缩短
        # 页面导航+加载本身已占 3-4s，仅需补足最小安全间隔差值
        from crawler.account_pool import compute_dynamic_interval
        _rate_mult_reply = get_tracker().get_sleep_multiplier("tweet_detail", task_id=task_id)
        _min_r, _max_r, _ = compute_dynamic_interval("tweet_detail")
        _nav_latency_compensation = 5.0  # 导航+页面加载+首次包等待实际消耗
        _target_interval = random.uniform(_min_r, _max_r) * _rate_mult_reply
        _actual_sleep = max(0.3, _target_interval - _nav_latency_compensation)
        interruptible_sleep(_actual_sleep, task_id=task_id)

    # ── 清理 batch 级共享 tab ──────────────────────────────────────
    if _owns_shared_tab and _shared_reply_tab:
        try:
            _shared_reply_tab.close()
        except Exception:
            pass

    # ── 批次完成后注册指纹（供后续任务去重复用） ──────────────────
    if dedup_enabled and task_id:
        register_tweets(updated_tweets, task_id)
        if dedup_hit_count:
            logger.info(
                f"[{tag}] 本批去重统计: {dedup_hit_count}/{len(tweets)} 条推文命中缓存"
            )

    return updated_tweets, failed_records
