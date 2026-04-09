from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _TimeoutButLoadedTab:
    def __init__(self) -> None:
        self.url = "https://s.weibo.com/weibo?q=%E5%A4%A7%E6%A8%A1%E5%9E%8B&page=19"
        self.html = "<html>" + ("x" * 3000) + "</html>"

    def get(self, *_args, **_kwargs):
        raise TimeoutError("timeout | method=Page.stopLoading")


class _TimeoutAndEmptyTab:
    def __init__(self) -> None:
        self.url = "https://s.weibo.com/weibo?q=%E5%A4%A7%E6%A8%A1%E5%9E%8B&page=19"
        self.html = ""

    def get(self, *_args, **_kwargs):
        raise TimeoutError("timeout | method=Page.stopLoading")


class _TimeoutAndBrokenTab:
    def get(self, *_args, **_kwargs):
        raise TimeoutError("timeout | method=Page.stopLoading")

    @property
    def url(self):
        raise TimeoutError("timeout | method=Target.getTargetInfo")

    @property
    def html(self):
        raise TimeoutError("timeout | method=DOM.getDocument")


class _JsReadyTab:
    def __init__(self) -> None:
        self._url = "https://s.weibo.com"

    def run_js(self, script, timeout=None):
        if "window.location.href =" in script:
            self._url = "https://s.weibo.com/weibo?q=%E5%A4%A7%E6%A8%A1%E5%9E%8B&page=4"
            return None
        if "return {" in script:
            return {
                "href": self._url,
                "readyState": "interactive",
                "bodyTextLength": 1500,
                "cardCount": 8,
                "htmlLength": 6000,
            }
        if "document.documentElement" in script:
            return "<html>" + ("x" * 5000) + "</html>"
        raise AssertionError(f"unexpected script: {script}")


def test_safe_get_html_reuses_dom_when_stop_loading_times_out(monkeypatch):
    from crawler.weibo import searcher

    monkeypatch.setattr(searcher, "_check_anti_crawl", lambda _tab: None)
    monkeypatch.setattr("crawler.weibo.http_418_guard.detect_weibo_http_418", lambda _tab: False)

    html, error = searcher._safe_get_html(
        _TimeoutButLoadedTab(),
        "https://s.weibo.com/weibo?q=%E5%A4%A7%E6%A8%A1%E5%9E%8B&page=19",
    )

    assert error is None
    assert html is not None
    assert len(html) > 2000


def test_safe_get_html_returns_precise_timeout_message_when_dom_not_ready(monkeypatch):
    from crawler.weibo import searcher

    monkeypatch.setattr(searcher, "_check_anti_crawl", lambda _tab: None)
    monkeypatch.setattr("crawler.weibo.http_418_guard.detect_weibo_http_418", lambda _tab: False)

    html, error = searcher._safe_get_html(
        _TimeoutAndEmptyTab(),
        "https://s.weibo.com/weibo?q=%E5%A4%A7%E6%A8%A1%E5%9E%8B&page=19",
    )

    assert html is None
    assert error is not None
    assert error.startswith("[timeout] 页面导航超时")
    assert "浏览器/标签页可能仍在线" in error


def test_safe_get_html_does_not_raise_when_timeout_followed_by_tab_probe_timeout(monkeypatch):
    from crawler.weibo import searcher

    monkeypatch.setattr(searcher, "_check_anti_crawl", lambda _tab: None)
    monkeypatch.setattr("crawler.weibo.http_418_guard.detect_weibo_http_418", lambda _tab: False)

    html, error = searcher._safe_get_html(
        _TimeoutAndBrokenTab(),
        "https://s.weibo.com/weibo?q=%E5%A4%A7%E6%A8%A1%E5%9E%8B&page=19",
    )

    assert html is None
    assert error is not None
    assert error.startswith("[timeout] 页面导航超时")
    assert "读取 tab.url 失败" in error or "读取 tab.html 失败" in error


def test_safe_get_html_prefers_js_navigation_fast_path_for_weibo_search(monkeypatch):
    from crawler.weibo import searcher

    monkeypatch.setattr("crawler.weibo.http_418_guard.detect_weibo_http_418", lambda _tab: False)

    html, error = searcher._safe_get_html(
        _JsReadyTab(),
        "https://s.weibo.com/weibo?q=%E5%A4%A7%E6%A8%A1%E5%9E%8B&page=4",
    )

    assert error is None
    assert html is not None
    assert len(html) > 4000
