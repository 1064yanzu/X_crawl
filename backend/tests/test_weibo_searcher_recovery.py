from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _LoadMode:
    def __init__(self) -> None:
        self.eager_called = 0

    def eager(self) -> None:
        self.eager_called += 1


class _SetProxy:
    def __init__(self) -> None:
        self.load_mode = _LoadMode()


class _RebuildTab:
    def __init__(self) -> None:
        self.set = _SetProxy()
        self.calls: list[tuple[str, int]] = []

    def get(self, url: str, timeout: int = 0) -> None:
        self.calls.append((url, timeout))


class _ReusePageTab:
    def __init__(self, url: str, html: str) -> None:
        self.url = url
        self.html = html


def test_rebuild_weibo_tab_restores_eager_mode(monkeypatch):
    from crawler.weibo import searcher

    tab = _RebuildTab()
    injected: list[dict] = []

    monkeypatch.setattr(searcher, "_get_fresh_tab", lambda browser_instance=None: tab)
    monkeypatch.setattr("crawler.weibo.searcher.time.sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("crawler.weibo.cookie_manager.inject_cookies_to_tab", lambda _tab, cookies: injected.extend(cookies))
    monkeypatch.setattr("crawler.weibo.auth._get_account_cookies", lambda account_cookies=None: [{"name": "SUB", "value": "x"}])

    rebuilt = searcher._rebuild_weibo_tab()

    assert rebuilt is tab
    assert tab.calls == [("https://s.weibo.com", 15)]
    assert injected == [{"name": "SUB", "value": "x"}]
    assert tab.set.load_mode.eager_called == 1


def test_try_reuse_current_search_page_reuses_matching_page_html():
    from crawler.weibo import searcher

    html, error = searcher._try_reuse_current_search_page(
        _ReusePageTab(
            "https://s.weibo.com/weibo?q=test&page=7",
            "<html>" + ("x" * 2500) + "</html>",
        ),
        expected_page=7,
    )

    assert error is None
    assert html is not None
    assert len(html) > 2000


def test_try_reuse_current_search_page_rejects_mismatched_page():
    from crawler.weibo import searcher

    html, error = searcher._try_reuse_current_search_page(
        _ReusePageTab(
            "https://s.weibo.com/weibo?q=test&page=8",
            "<html>" + ("x" * 2500) + "</html>",
        ),
        expected_page=7,
    )

    assert html is None
    assert error is not None
    assert "当前页码不是目标页" in error
