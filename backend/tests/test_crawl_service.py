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
