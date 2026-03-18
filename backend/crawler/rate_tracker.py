"""
X 平台速率限制追踪器

解析 API 响应头中的 x-rate-limit-remaining/limit/reset，
动态调整爬取速度，避免触发 429 错误。
"""
import time
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# X 平台速率限制参考（实测值）
# 搜索接口：50次/15分钟
# 评论接口：150次/15分钟
_ENDPOINT_LIMITS = {
    "search": 50,
    "tweet_detail": 150,
}


class RateLimitTracker:
    """线程安全的速率限制状态追踪"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # endpoint_type → {remaining, limit, reset_ts, updated_at}
        self._state: dict[str, dict] = {}

    def update(self, endpoint_type: str, remaining: int, limit: int, reset_ts: int) -> None:
        """更新指定端点的速率限制状态"""
        with self._lock:
            self._state[endpoint_type] = {
                "remaining": remaining,
                "limit": limit,
                "reset_ts": reset_ts,
                "updated_at": time.time(),
            }
        pct = remaining / limit * 100 if limit > 0 else 100
        logger.debug(f"速率限制更新 [{endpoint_type}]: {remaining}/{limit} ({pct:.0f}%)")

    def get_sleep_multiplier(self, endpoint_type: str) -> float:
        """根据剩余配额返回睡眠时间倍数（用于 jittered_sleep 乘法）"""
        with self._lock:
            s = self._state.get(endpoint_type)
        if not s or s["limit"] == 0:
            return 1.0
        # 超过 5 分钟的数据视为过期
        if time.time() - s["updated_at"] > 300:
            return 1.0
        pct = s["remaining"] / s["limit"]
        if pct > 0.6:
            return 1.0   # 激进模式：剩余 > 60%
        if pct > 0.3:
            return 1.3   # 标准模式：剩余 30-60%
        if pct > 0.1:
            return 2.0   # 保守模式：剩余 10-30%
        return 3.0       # 临界模式：剩余 < 10%，配合 maybe_wait_for_reset

    def maybe_wait_for_reset(self, endpoint_type: str, task_id: Optional[str] = None) -> None:
        """若剩余配额 < 5%，先尝试切换账号；无可用账号时才主动等待 reset"""
        with self._lock:
            s = self._state.get(endpoint_type)
        if not s or s["limit"] == 0:
            return
        pct = s["remaining"] / s["limit"]
        if pct >= 0.05:
            return
        wait = max(0.0, s["reset_ts"] - time.time() + 2.0)
        if wait <= 0 or wait >= 900:
            return
        logger.warning(
            f"速率限制将尽 ({s['remaining']}/{s['limit']}, {pct*100:.1f}%)，"
            f"尝试切换账号或等待重置 {wait:.0f}s ..."
        )
        # 先尝试切换账号避免等待
        try:
            from crawler.account_pool import get_pool
            pool = get_pool()
            if pool.get_active_account_count() > 1:
                logger.info(
                    f"速率限制将尽，账号池有 {pool.get_active_account_count()} 个账号，跳过等待"
                )
                return
        except Exception:
            pass
        from crawler.utils import interruptible_sleep
        interruptible_sleep(wait, task_id=task_id)

    def get_reset_ts(self, endpoint_type: str) -> int:
        """获取指定端点的限速重置时间戳（0 = 未知）"""
        with self._lock:
            s = self._state.get(endpoint_type, {})
            return s.get("reset_ts", 0)

    def get_remaining_pct(self, endpoint_type: str) -> float:
        """获取指定端点剩余配额百分比（1.0 = 尚未使用或不局）"""
        with self._lock:
            s = self._state.get(endpoint_type)
        if not s or s.get("limit", 0) == 0:
            return 1.0
        if time.time() - s.get("updated_at", 0) > 300:
            return 1.0
        return s["remaining"] / s["limit"]


def extract_rate_headers(packet) -> Optional[tuple[str, int, int, int]]:
    """从数据包提取速率限制头。

    Returns:
        (endpoint_type, remaining, limit, reset_ts) 或 None
    """
    try:
        headers = packet.response.headers
        if not headers:
            return None
        remaining = int(headers.get("x-rate-limit-remaining", -1))
        limit = int(headers.get("x-rate-limit-limit", -1))
        reset_ts = int(headers.get("x-rate-limit-reset", 0))
        if remaining < 0 or limit <= 0:
            return None
        url = getattr(packet, "url", "") or ""
        if "SearchTimeline" in url:
            endpoint = "search"
        elif "TweetDetail" in url:
            endpoint = "tweet_detail"
        else:
            endpoint = "other"
        return endpoint, remaining, limit, reset_ts
    except Exception:
        return None


# 模块级单例
_tracker = RateLimitTracker()


def get_tracker() -> RateLimitTracker:
    """获取模块级速率限制追踪器单例"""
    return _tracker
