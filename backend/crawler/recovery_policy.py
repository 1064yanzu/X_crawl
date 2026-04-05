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
    cloudflare_wait_seconds: float

    @classmethod
    def from_settings(cls, settings_obj) -> "RecoveryPolicy":
        return cls(
            packet_soft_retries=max(0, int(settings_obj.crawler_packet_soft_retries)),
            refresh_max_retries=max(1, int(settings_obj.crawler_refresh_max_retries)),
            challenge_retry_times=max(0, int(settings_obj.crawler_challenge_retry_times)),
            challenge_cooldown=max(0.0, float(settings_obj.crawler_challenge_cooldown)),
            cloudflare_wait_seconds=max(
                10.0,
                float(getattr(settings_obj, "crawler_cloudflare_wait_seconds", 60.0)),
            ),
        )


@dataclass(slots=True)
class ChallengeWaitPlan:
    seconds: float
    is_cloudflare: bool


def backoff_seconds(attempt: int, *, base: float = 2.0, cap: float = 40.0) -> float:
    return min(cap, base * (2 ** max(0, attempt)))


def sleep_with_jitter(seconds: float, *, jitter_ratio: float = 0.2, minimum: float = 0.3) -> None:
    jitter = seconds * jitter_ratio
    actual = seconds + random.uniform(-jitter, jitter)
    time.sleep(max(minimum, actual))


def build_challenge_wait_plan(
    tab,
    *,
    challenge_cooldown: float,
    cloudflare_wait_seconds: float,
) -> ChallengeWaitPlan:
    try:
        from crawler.page_state import detect_cloudflare_challenge

        is_cloudflare = bool(detect_cloudflare_challenge(tab))
    except Exception:
        is_cloudflare = False

    if is_cloudflare:
        return ChallengeWaitPlan(
            seconds=max(10.0, float(cloudflare_wait_seconds)),
            is_cloudflare=True,
        )

    return ChallengeWaitPlan(
        seconds=max(0.0, float(challenge_cooldown)),
        is_cloudflare=False,
    )


def wait_for_challenge(plan: ChallengeWaitPlan, *, task_id: str | None = None) -> None:
    if plan.is_cloudflare:
        from crawler.utils import interruptible_sleep

        interruptible_sleep(plan.seconds, task_id=task_id)
        return

    sleep_with_jitter(plan.seconds, jitter_ratio=0.1, minimum=0.8)


def soft_recover_for_packet(tab, attempt: int) -> None:
    """超时后的轻量恢复：检测 Retry 按钮 → 小步滚动 + 短等待。"""
    # 优先：若出现 X 错误页 Retry 按钮，直接点击触发内容重新加载
    try:
        from crawler.page_state import click_retry_button_if_present
        clicked = click_retry_button_if_present(tab)
        if clicked:
            time.sleep(0.8)
            return
    except Exception:
        pass

    wait = backoff_seconds(attempt, base=0.3, cap=2.0)
    sleep_with_jitter(wait, jitter_ratio=0.2, minimum=0.2)
    try:
        tab.scroll.down(280)
    except Exception:
        pass
