from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummyTab:
    def __init__(self) -> None:
        self.url = ""
        self.html = "<html></html>"
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _DummyPost:
    def __init__(self, mid: str) -> None:
        self.mid = mid
        self.comments_count = 0
        self.author_id = "author"
        self.url = f"https://weibo.com/{mid}"

    def to_dict(self) -> dict:
        return {"id": self.mid, "mid": self.mid, "text": f"post-{self.mid}"}


def test_weibo_segment_search_reuses_same_tab_and_session(monkeypatch):
    from crawler.weibo import searcher, auth, date_splitter, html_parser
    from crawler import utils

    tab = _DummyTab()
    tab_calls = {"get_tab": 0, "login": 0, "search_cookie": 0, "safe_get_html": 0}

    def fake_get_tab_with_retry(max_retries: int = 2, browser_instance=None):
        tab_calls["get_tab"] += 1
        return tab

    def fake_ensure_weibo_login(_tab, account_cookies=None):
        tab_calls["login"] += 1
        return True

    def fake_ensure_search_cookies(_tab, account_cookies=None):
        tab_calls["search_cookie"] += 1

    def fake_split_date_range(*args, **kwargs):
        return [("2023-01-01", "2023-01-31"), ("2023-02-01", "2023-02-28")]

    def fake_safe_get_html(_tab, url: str, wait_seconds: float = 3.0):
        tab_calls["safe_get_html"] += 1
        _tab.url = url
        _tab.html = "<html>ok</html>"
        return _tab.html, None

    page_state = {"count": 0}

    def fake_parse_search_page(html: str):
        page_state["count"] += 1
        return [_DummyPost(str(page_state["count"]))], False, 1

    monkeypatch.setattr(searcher, "_get_tab_with_retry", fake_get_tab_with_retry)
    monkeypatch.setattr(searcher, "_safe_get_html", fake_safe_get_html)
    monkeypatch.setattr(auth, "ensure_weibo_login", fake_ensure_weibo_login)
    monkeypatch.setattr(auth, "ensure_search_cookies", fake_ensure_search_cookies)
    monkeypatch.setattr(date_splitter, "split_date_range", fake_split_date_range)
    monkeypatch.setattr(html_parser, "parse_search_page", fake_parse_search_page)
    monkeypatch.setattr(utils, "check_signal", lambda task_id=None: None)
    monkeypatch.setattr(utils, "jittered_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "interruptible_sleep", lambda *args, **kwargs: None)

    result = searcher.search(
        keyword="测试关键词",
        max_count=0,
        task_id=None,
        resume=False,
        fetch_comments=False,
        start_date="2023-01-01",
        end_date="2023-02-28",
    )

    assert len(result.posts) == 2
    assert tab_calls["get_tab"] == 1
    assert tab_calls["login"] == 1
    assert tab_calls["search_cookie"] == 1
    assert tab_calls["safe_get_html"] == 2
    assert tab.closed is True
