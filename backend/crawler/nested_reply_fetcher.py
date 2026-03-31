"""
二级评论递归抓取模块

职责：给定一级评论列表，遍历 reply_count > 0 的评论，
递归调用 fetch_replies 获取子评论，存入 reply["replies"]。
"""
import logging
from typing import Optional

from crawler.crawl_signals import StopSignal, ChallengeSignal
from crawler.utils import check_signal, jittered_sleep
from config import settings

logger = logging.getLogger(__name__)


def fetch_nested_replies(
    replies: list[dict],
    *,
    current_depth: int = 1,
    max_depth: int = 2,
    max_replies_per_tweet: int = 0,
    task_id: Optional[str] = None,
    timeout: Optional[float] = None,
    browser_instance=None,
) -> tuple[list[dict], list[dict]]:
    """
    递归抓取评论的子评论。

    Args:
        replies:              一级（或 N 级）评论列表
        current_depth:        当前深度（1 表示正在处理一级评论）
        max_depth:            最大深度（2 = 原帖→一级→二级）
        max_replies_per_tweet: 每条评论最多抓取的子评论数
        task_id:              任务 ID（用于信号检查 + 原始响应存储）
        timeout:              等待数据包超时（秒）

    Returns:
        (updated_replies, failed_records)
        - updated_replies: 更新后的评论列表（带 reply["replies"]）
        - failed_records:  抓取失败记录列表
    """
    # 延迟导入避免循环引用
    from crawler.reply_fetcher import fetch_replies as _fetch_replies

    if current_depth >= max_depth:
        logger.debug(f"已达最大评论深度 {max_depth}，跳过子评论抓取")
        return replies, []

    failed_records: list[dict] = []

    # 筛选有子评论的评论
    candidates = [
        (i, r) for i, r in enumerate(replies)
        if (r.get("metrics") or {}).get("replies", 0) > 0
        and r.get("replies") is None  # 未抓取过
    ]

    if not candidates:
        logger.debug(f"深度 {current_depth + 1}: 无需抓取子评论（0 条候选）")
        return replies, []

    logger.info(
        f"开始抓取第 {current_depth + 1} 级评论："
        f"{len(candidates)}/{len(replies)} 条评论有子评论"
    )

    import api.services.task_manager as _task_mgr

    for seq, (idx, reply) in enumerate(candidates):
        # 信号检查
        try:
            check_signal(task_id)
        except StopSignal:
            # 中断时标记未处理的评论为空回复
            for _, (future_idx, future_reply) in enumerate(candidates[seq:]):
                if future_reply.get("replies") is None:
                    reply_copy = dict(future_reply)
                    reply_copy["replies"] = []
                    replies[future_idx] = reply_copy
            raise

        reply_id = reply.get("id", "")
        reply_screen_name = (reply.get("author") or {}).get("screen_name", "")
        reply_count = (reply.get("metrics") or {}).get("replies", 0)

        if not reply_id or not reply_screen_name:
            logger.warning(f"评论缺少 id 或 screen_name，跳过子评论抓取")
            continue

        # 更新阶段提示
        if task_id:
            _task_mgr.update_task_phase(
                task_id,
                f"正在抓取第 {current_depth + 1} 级评论 "
                f"({seq + 1}/{len(candidates)}, "
                f"@{reply_screen_name}, 预期 {reply_count} 条)..."
            )

        logger.info(
            f"  [{current_depth + 1}级] 进度 {seq + 1}/{len(candidates)}: "
            f"reply_id={reply_id}, 预期 {reply_count} 条子评论"
        )

        try:
            sub_replies, failure_info = _fetch_replies(
                tweet_id=reply_id,
                screen_name=reply_screen_name,
                reply_limit=max_replies_per_tweet,
                task_id=task_id,
                timeout=timeout,
                expected_count=reply_count,
                browser_instance=browser_instance,
            )

            reply_copy = dict(reply)
            reply_copy["replies"] = sub_replies
            replies[idx] = reply_copy

            if failure_info:
                failure_info["task_id"] = task_id or ""
                failure_info["depth"] = current_depth + 1
                failed_records.append(failure_info)

            # 如果还允许更深层级，递归处理
            if sub_replies and current_depth + 1 < max_depth:
                sub_replies, sub_failed = fetch_nested_replies(
                    sub_replies,
                    current_depth=current_depth + 1,
                    max_depth=max_depth,
                    max_replies_per_tweet=max_replies_per_tweet,
                    task_id=task_id,
                    timeout=timeout,
                    browser_instance=browser_instance,
                )
                reply_copy["replies"] = sub_replies
                failed_records.extend(sub_failed)

        except StopSignal:
            reply_copy = dict(reply)
            reply_copy["replies"] = []
            replies[idx] = reply_copy
            raise
        except ChallengeSignal:
            raise
        except Exception as e:
            logger.error(
                f"抓取 reply_id={reply_id} 子评论失败: {e}",
                exc_info=True,
            )
            reply_copy = dict(reply)
            reply_copy["replies"] = []
            replies[idx] = reply_copy
            failed_records.append({
                "task_id": task_id or "",
                "tweet_id": reply_id,
                "screen_name": reply_screen_name,
                "expected_count": reply_count,
                "fetched_count": 0,
                "depth": current_depth + 1,
                "error_reason": f"异常: {str(e)[:200]}",
            })

        # 礼貌性间隔：嵌套评论间隔缩短，导航本身已贡献延迟，且同属一次用户浏览行为
        from crawler.account_pool import compute_dynamic_interval
        from crawler.rate_tracker import get_tracker as _get_tracker
        from crawler.utils import interruptible_sleep as _interruptible_sleep
        import random as _random
        _rate_mult_nested = _get_tracker().get_sleep_multiplier("tweet_detail", task_id=task_id)
        _min_n, _max_n, _ = compute_dynamic_interval("tweet_detail")
        # 嵌套评论使用缩短的间隔，导航本身已贡献 3-5s 延迟
        _nested_interval = _random.uniform(_min_n * 0.3, _max_n * 0.4) * _rate_mult_nested
        _interruptible_sleep(max(0.5, _nested_interval - 4.0), task_id=task_id)

    total_sub = sum(
        len(r.get("replies", []))
        for _, r in enumerate(replies)
        if r.get("replies")
    )
    logger.info(
        f"第 {current_depth + 1} 级评论抓取完成：共 {total_sub} 条子评论"
    )

    return replies, failed_records
