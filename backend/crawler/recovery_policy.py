"""统一恢复策略：软重试、指数退避与挑战页冷却。"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass(slots=True)
class RecoveryPolicy:
    packet_soft_retries: int
    refresh_max_retries: int
    challenge_retry_times: int
    challenge_cooldown: float

    @classmethod
    def from_settings(cls, settings_obj) -> "RecoveryPolicy":
        return cls(
            packet_soft_retries=max(0, int(settings_obj.crawler_packet_soft_retries)),
            refresh_max_retries=max(1, int(settings_obj.crawler_refresh_max_retries)),
            challenge_retry_times=max(0, int(settings_obj.crawler_challenge_retry_times)),
            challenge_cooldown=max(0.0, float(settings_obj.crawler_challenge_cooldown)),
        )


def backoff_seconds(attempt: int, *, base: float = 2.0, cap: float = 40.0) -> float:
    return min(cap, base * (2 ** max(0, attempt)))


def sleep_with_jitter(seconds: float, *, jitter_ratio: float = 0.2, minimum: float = 0.3) -> None:
    jitter = seconds * jitter_ratio
    actual = seconds + random.uniform(-jitter, jitter)
    time.sleep(max(minimum, actual))


def soft_recover_for_packet(tab, attempt: int) -> None:
    """超时后的轻量恢复：小步滚动 + 短等待。"""
    wait = backoff_seconds(attempt, base=0.5, cap=2.5)
    sleep_with_jitter(wait, jitter_ratio=0.2, minimum=0.3)
    try:
        tab.scroll.down(280)
    except Exception:
        pass
