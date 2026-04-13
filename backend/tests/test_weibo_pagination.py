from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummyNextButton:
    def __init__(self, tab) -> None:
        self._tab = tab
        self.clicked = 0

    def attr(self, name: str) -> str:
        if name != "href":
            raise AssertionError(f"unexpected attr: {name}")
        return "/weibo?q=test&page=2"

    def click(self) -> None:
        self.clicked += 1
        self._tab._url = "https://s.weibo.com/weibo?q=test&page=2"
        self._tab._html = "<html>" + ("x" * 3000) + "</html>"


class _ClickDrivenTab:
    def __init__(self) -> None:
        self._url = "https://s.weibo.com/weibo?q=test&page=1"
        self._html = "<html>" + ("x" * 3000) + "</html>"
        self.next_button = _DummyNextButton(self)

    def ele(self, selector: str, timeout: float = 0):
        if selector in ("css:a.next", "text:下一页"):
            return self.next_button
        raise AssertionError(f"unexpected selector: {selector}")

    @property
    def url(self) -> str:
        return self._url

    @property
    def html(self) -> str:
        return self._html

    def get(self, *_args, **_kwargs):
        raise AssertionError("click_next_page 不应再回退到 tab.get()")


class _BrokenProbeButton:
    def attr(self, name: str) -> str:
        return "/weibo?q=test&page=2"

    def click(self) -> None:
        return None


class _BrokenProbeTab:
    def ele(self, selector: str, timeout: float = 0):
        if selector in ("css:a.next", "text:下一页"):
            return _BrokenProbeButton()
        raise AssertionError(f"unexpected selector: {selector}")

    @property
    def url(self):
        raise TimeoutError("timeout | method=Target.getTargetInfo")

    @property
    def html(self):
        raise TimeoutError("timeout | method=DOM.getDocument")


def test_click_next_page_uses_real_click_instead_of_tab_get(monkeypatch):
    from crawler.weibo import pagination

    monkeypatch.setattr("crawler.weibo.http_418_guard.detect_weibo_http_418", lambda _tab: False)

    tab = _ClickDrivenTab()
    html, error = pagination.click_next_page(tab, expected_page=2, timeout=3.0)

    assert error is None
    assert html is not None
    assert len(html) > 2000
    assert tab.next_button.clicked == 1


def test_click_next_page_marks_cdp_dead_when_probe_times_out(monkeypatch):
    from crawler.weibo import pagination

    tick = {"value": 0.0}

    def fake_monotonic() -> float:
        tick["value"] += 1.0
        return tick["value"]

    monkeypatch.setattr("crawler.weibo.http_418_guard.detect_weibo_http_418", lambda _tab: False)
    monkeypatch.setattr(pagination.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pagination.time, "monotonic", fake_monotonic)

    html, error = pagination.click_next_page(_BrokenProbeTab(), expected_page=2, timeout=3.0)

    assert html is None
    assert error is not None
    assert "CDP_DEAD" in error
