from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummyTab:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class _DummyBrowserInstance:
    def __init__(self, tab: _DummyTab) -> None:
        self._tab = tab

    def new_tab(self) -> _DummyTab:
        return self._tab


def test_inject_account_cookies_closes_temp_tab_on_success(monkeypatch):
    import crawler.account_pool as account_pool
    import crawler.auth as auth
    from api.services import crawl_service

    tab = _DummyTab()
    account = SimpleNamespace(alias="@tester")
    pool = SimpleNamespace(
        get_account=lambda account_id: account,
        mark_account_used=lambda account_id: None,
    )

    monkeypatch.setattr(account_pool, "get_pool", lambda: pool)
    monkeypatch.setattr(auth, "inject_account_cookies", lambda current_tab, current_account: 2)

    crawl_service._inject_account_cookies(
        "task-1",
        "acc-1",
        browser_instance=_DummyBrowserInstance(tab),
    )

    assert tab.closed == 1


def test_inject_account_cookies_closes_temp_tab_on_error(monkeypatch):
    import crawler.account_pool as account_pool
    import crawler.auth as auth
    from api.services import crawl_service

    tab = _DummyTab()
    account = SimpleNamespace(alias="@tester")
    pool = SimpleNamespace(
        get_account=lambda account_id: account,
        mark_account_used=lambda account_id: None,
    )

    monkeypatch.setattr(account_pool, "get_pool", lambda: pool)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("inject failed")

    monkeypatch.setattr(auth, "inject_account_cookies", _raise)

    crawl_service._inject_account_cookies(
        "task-1",
        "acc-1",
        browser_instance=_DummyBrowserInstance(tab),
    )

    assert tab.closed == 1


def test_youtube_video_urls_keeps_zero_max_videos_as_unlimited(monkeypatch):
    from api.services import crawl_service
    from crawler.youtube.searcher import YouTubeCrawlResult
    import crawler.youtube.searcher as youtube_searcher

    captured: dict[str, object] = {}

    def fake_crawl_by_video_ids(**kwargs):
        captured.update(kwargs)
        videos = [
            {"id": str(idx), "platform": "youtube", "replies": []}
            for idx in range(len(kwargs.get("video_urls") or []))
        ]
        return YouTubeCrawlResult(videos=videos, replies_fetched=0)

    monkeypatch.setattr(youtube_searcher, "crawl_by_video_ids", fake_crawl_by_video_ids)
    monkeypatch.setattr(crawl_service.task_manager, "update_task_phase", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.task_manager, "update_task_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service.telemetry, "record_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_service, "get_metrics", lambda *args, **kwargs: {})

    status = crawl_service._run_youtube_task(
        task_id="yt-video-urls",
        keyword="youtube-urls · 453 视频",
        youtube_params={
            "source": "video_urls",
            "video_urls": [f"https://youtu.be/video{idx:06d}" for idx in range(453)],
            "max_videos": 0,
        },
    )

    assert status == "done"
    assert captured["max_videos"] == 0
    assert len(captured["video_urls"]) == 453
