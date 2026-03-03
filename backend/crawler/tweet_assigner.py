"""
推文任务分配器

将推文列表按评论数（预期回复数）负载均衡地分配给多个账号。
使用 LPT（Longest Processing Time）算法：
  1. 按预期评论数降序排列推文
  2. 最小堆贪心：每次将当前最重的推文分配给当前负载最低的账号

这是经典的 makespan 最小化近似，实践效果接近最优。

示例：
    3 个账号，推文评论数 [200, 150, 100, 80, 50]
    → 账号A: 200 + 50 = 250
    → 账号B: 150 + 80 = 230
    → 账号C: 100       = 100
"""
import heapq
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crawler.account_pool import AccountEntry

logger = logging.getLogger(__name__)


def assign_tweets_to_accounts(
    tweets: list[dict],
    accounts: list["AccountEntry"],
) -> list[str]:
    """
    按评论数负载均衡分配推文到账号。

    Args:
        tweets:   推文列表，需含 metrics.replies 字段
        accounts: 可用账号列表（已过滤：enabled=True, is_valid=True, not is_rate_limited）

    Returns:
        与 tweets 等长的 account_id 列表，result[i] 表示 tweets[i] 分配给哪个账号
    """
    if not accounts:
        return [""] * len(tweets)
    if len(accounts) == 1:
        return [accounts[0].account_id] * len(tweets)

    n = len(tweets)

    # 按预期评论数降序排列（保留原始索引）
    sorted_indices = sorted(
        range(n),
        key=lambda i: (tweets[i].get("metrics") or {}).get("replies", 0),
        reverse=True,
    )

    # 最小堆：(当前总负载, 稳定序号, account_id)
    # 稳定序号保证相同负载时优先选固定账号（避免无意义的切换）
    heap = [(0, seq, acc.account_id) for seq, acc in enumerate(accounts)]
    heapq.heapify(heap)

    assignment = [""] * n

    for tweet_idx in sorted_indices:
        reply_count = max(1, (tweets[tweet_idx].get("metrics") or {}).get("replies", 0))
        load, seq, acc_id = heapq.heappop(heap)
        assignment[tweet_idx] = acc_id
        heapq.heappush(heap, (load + reply_count, seq, acc_id))

    _log_assignment_summary(tweets, accounts, assignment)
    return assignment


def reassign_remaining_tweets(
    assignment: list[str],
    account_map: dict,
    frozen_account_id: str,
    start_idx: int,
    pool,
) -> None:
    """
    将冻结账号未处理的推文重新轮询分配给其他活跃账号。

    Args:
        assignment:        当前分配列表（原地修改）
        account_map:       account_id → AccountEntry 映射（原地更新）
        frozen_account_id: 被冻结账号的 ID
        start_idx:         从哪条推文开始重新分配（含）
        pool:              账号池实例
    """
    new_active = [
        a for a in pool.list_accounts()
        if a.enabled and a.is_valid and not a.is_rate_limited
        and a.account_id != frozen_account_id
    ]

    if not new_active:
        logger.warning("无其他可用账号，冻结账号的剩余推文将不注入 Cookie")
        for j in range(start_idx, len(assignment)):
            if assignment[j] == frozen_account_id:
                assignment[j] = ""
        return

    # 更新 account_map（让外层函数也能看到新增的账号）
    for a in new_active:
        account_map[a.account_id] = a

    rr_idx = 0
    reassigned = 0
    for j in range(start_idx, len(assignment)):
        if assignment[j] == frozen_account_id:
            assignment[j] = new_active[rr_idx % len(new_active)].account_id
            rr_idx += 1
            reassigned += 1

    if reassigned > 0:
        logger.info(
            f"冻结账号剩余 {reassigned} 条推文已重新分配至 "
            f"{[a.alias for a in new_active]}"
        )


# ─── 日志辅助 ─────────────────────────────────────────────────────────────────

def _log_assignment_summary(
    tweets: list[dict],
    accounts: list["AccountEntry"],
    assignment: list[str],
) -> None:
    for acc in accounts:
        indices = [i for i, a in enumerate(assignment) if a == acc.account_id]
        total_replies = sum(
            (tweets[i].get("metrics") or {}).get("replies", 0) for i in indices
        )
        logger.info(
            f"[分配] 账号 {acc.alias!r}: {len(indices)} 条推文，"
            f"预计评论 {total_replies} 条"
        )
