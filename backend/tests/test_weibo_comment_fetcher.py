from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_open_post_page_with_retry_returns_navigation_timeout_on_repeated_errors(monkeypatch):
    from crawler.weibo import comment_fetcher

    class _TimeoutTab:
        def get(self, *_args, **_kwargs):
            raise TimeoutError("timeout | method=Page.stopLoading")

    monkeypatch.setattr("crawler.utils.interruptible_sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("crawler.weibo.http_418_guard.detect_weibo_http_418", lambda _tab: False)
    monkeypatch.setattr(
        "crawler.weibo.http_418_guard.wait_weibo_http_418_cooldown",
        lambda **_kwargs: None,
    )

    opened, reason = comment_fetcher._open_post_page_with_retry(
        _TimeoutTab(),
        page_url="https://weibo.com/123/detail",
        task_id="task-weibo-timeout",
    )

    assert opened is False
    assert reason == "navigation_timeout"
