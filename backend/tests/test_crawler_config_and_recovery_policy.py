from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.routers import crawler_config
from crawler.recovery_policy import (
    RecoveryPolicy,
    build_challenge_wait_plan,
    wait_for_challenge,
)
from crawler.weibo.http_418_guard import (
    detect_weibo_http_418,
    wait_weibo_http_418_cooldown,
)


def test_recovery_policy_reads_cloudflare_wait_seconds():
    policy = RecoveryPolicy.from_settings(
        SimpleNamespace(
            crawler_packet_soft_retries=2,
            crawler_refresh_max_retries=3,
            crawler_challenge_retry_times=4,
            crawler_challenge_cooldown=8.0,
            crawler_cloudflare_wait_seconds=75.0,
        )
    )

    assert policy.cloudflare_wait_seconds == 75.0


def test_build_challenge_wait_plan_prefers_cloudflare_wait(monkeypatch):
    import crawler.page_state as page_state

    monkeypatch.setattr(page_state, "detect_cloudflare_challenge", lambda tab: True)

    plan = build_challenge_wait_plan(
        object(),
        challenge_cooldown=8.0,
        cloudflare_wait_seconds=90.0,
    )

    assert plan.is_cloudflare is True
    assert plan.seconds == 90.0


def test_wait_for_challenge_uses_interruptible_sleep_for_cloudflare(monkeypatch):
    calls: list[tuple[str, float, str | None]] = []

    import crawler.page_state as page_state
    import crawler.utils as crawler_utils
    import crawler.recovery_policy as recovery_policy

    monkeypatch.setattr(page_state, "detect_cloudflare_challenge", lambda tab: False)
    monkeypatch.setattr(
        crawler_utils,
        "interruptible_sleep",
        lambda seconds, task_id=None: calls.append(("interruptible", seconds, task_id)),
    )
    monkeypatch.setattr(
        recovery_policy,
        "sleep_with_jitter",
        lambda *args, **kwargs: calls.append(("jitter", float(args[0]), None)),
    )

    wait_for_challenge(
        build_challenge_wait_plan(
            object(),
            challenge_cooldown=8.0,
            cloudflare_wait_seconds=90.0,
        ),
        task_id="task-1",
    )

    assert calls == [("jitter", 8.0, None)]

    calls.clear()
    wait_for_challenge(
        recovery_policy.ChallengeWaitPlan(seconds=90.0, is_cloudflare=True),
        task_id="task-2",
    )
    assert calls == [("interruptible", 90.0, "task-2")]


def test_crawler_config_router_round_trips_cloudflare_wait_seconds(monkeypatch):
    persisted: dict[str, object] = {}
    resize_calls: list[int] = []

    monkeypatch.setattr(crawler_config, "set_settings_batch", lambda payload: persisted.update(payload))
    monkeypatch.setattr(crawler_config.scheduler, "reconfigure_backend", lambda: None)

    class _DummyPool:
        def resize(self, size: int) -> None:
            resize_calls.append(size)

    original = {
        "crawler_cloudflare_wait_seconds": crawler_config.settings.crawler_cloudflare_wait_seconds,
        "crawler_challenge_cooldown": crawler_config.settings.crawler_challenge_cooldown,
        "crawler_challenge_retry_times": crawler_config.settings.crawler_challenge_retry_times,
        "weibo_http_418_cooldown_seconds": crawler_config.settings.weibo_http_418_cooldown_seconds,
    }

    monkeypatch.setattr(
        "crawler.browser_pool.compute_pool_max_size",
        lambda max_tasks=None: max_tasks if max_tasks is not None else 1,
    )
    monkeypatch.setattr("crawler.browser_pool.get_browser_pool", lambda: _DummyPool())

    try:
        config = asyncio.run(crawler_config.get_crawler_config())
        assert config.crawler_cloudflare_wait_seconds == original["crawler_cloudflare_wait_seconds"]

        updated = asyncio.run(
            crawler_config.update_crawler_config(
                crawler_config.CrawlerConfig(
                    **{
                        **config.model_dump(),
                        "crawler_cloudflare_wait_seconds": 95.0,
                        "weibo_http_418_cooldown_seconds": 720.0,
                    }
                )
            )
        )

        assert updated.crawler_cloudflare_wait_seconds == 95.0
        assert updated.weibo_http_418_cooldown_seconds == 720.0
        assert crawler_config.settings.crawler_cloudflare_wait_seconds == 95.0
        assert crawler_config.settings.weibo_http_418_cooldown_seconds == 720.0
        assert persisted["crawler_cloudflare_wait_seconds"] == 95.0
        assert persisted["weibo_http_418_cooldown_seconds"] == 720.0
        assert resize_calls
    finally:
        crawler_config.settings.crawler_cloudflare_wait_seconds = original["crawler_cloudflare_wait_seconds"]
        crawler_config.settings.crawler_challenge_cooldown = original["crawler_challenge_cooldown"]
        crawler_config.settings.crawler_challenge_retry_times = original["crawler_challenge_retry_times"]
        crawler_config.settings.weibo_http_418_cooldown_seconds = original["weibo_http_418_cooldown_seconds"]


def test_detect_weibo_http_418_matches_browser_error_page():
    tab = SimpleNamespace(
        url="chrome-error://chromewebdata/",
        title="weibo",
        html="<html><body><h1>该网页无法正常运作</h1><div>HTTP ERROR 418</div></body></html>",
    )

    assert detect_weibo_http_418(tab) is True


def test_wait_weibo_http_418_cooldown_uses_interruptible_sleep(monkeypatch):
    calls: list[tuple[float, str | None]] = []
    phases: list[str] = []

    import crawler.weibo.http_418_guard as http_418_guard

    monkeypatch.setattr(
        http_418_guard,
        "interruptible_sleep",
        lambda seconds, task_id=None: calls.append((seconds, task_id)),
    )

    wait_weibo_http_418_cooldown(
        task_id="task-weibo-1",
        cooldown_seconds=600.0,
        context="搜索页",
        phase_callback=phases.append,
    )

    assert calls == [(600.0, "task-weibo-1")]
    assert phases and "HTTP 418" in phases[0]
