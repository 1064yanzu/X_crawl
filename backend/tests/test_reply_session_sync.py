from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummySetter:
    def __init__(self, recorder: list[dict]) -> None:
        self._recorder = recorder

    def cookies(self, cookie: dict) -> None:
        self._recorder.append(cookie)


class _DummyTab:
    def __init__(self) -> None:
        self.injected: list[dict] = []
        self.set = _DummySetter(self.injected)


class _DummyBrowserInstance:
    def __init__(self, cookies: list[dict]) -> None:
        self._cookies = list(cookies)
        self.synced: list[dict] = []
        self.bound_account_id: str | None = None
        self.bound_account_alias: str | None = None
        self.new_tab_calls = 0

    def get_cookies(self) -> list[dict]:
        return list(self._cookies)

    def set_cookies(
        self,
        cookies: list[dict],
        *,
        account_id: str | None = None,
        account_alias: str | None = None,
    ) -> None:
        self.synced = list(cookies)
        self.bound_account_id = account_id
        self.bound_account_alias = account_alias

    def get_bound_account(self) -> tuple[str | None, str | None]:
        return self.bound_account_id, self.bound_account_alias

    def new_tab(self):
        self.new_tab_calls += 1
        return object()


def test_reply_fetcher_uses_browser_instance_cookies_before_fallback(monkeypatch):
    from crawler import reply_fetcher

    tab = _DummyTab()
    browser_instance = _DummyBrowserInstance(
        [{"name": "auth_token", "value": "token", "domain": ".x.com"}]
    )
    states = iter([False, True])

    monkeypatch.setattr(reply_fetcher, "ensure_x_domain_context", lambda _tab: None)
    monkeypatch.setattr(reply_fetcher, "check_login", lambda _tab: next(states))
    monkeypatch.setattr(
        reply_fetcher,
        "ensure_login_detailed",
        lambda _tab: pytest.fail("不应回退到全局登录恢复"),
    )

    reply_fetcher._ensure_reply_session_ready(
        tab,
        task_id="task-sync",
        browser_instance=browser_instance,
    )

    assert len(tab.injected) == 1
    assert tab.injected[0]["name"] == "auth_token"


def test_reply_fetcher_raises_login_required_when_session_still_invalid(monkeypatch):
    from crawler import reply_fetcher
    from crawler.crawl_signals import ChallengeSignal

    tab = _DummyTab()

    monkeypatch.setattr(reply_fetcher, "ensure_x_domain_context", lambda _tab: None)
    monkeypatch.setattr(reply_fetcher, "check_login", lambda _tab: False)
    monkeypatch.setattr(
        reply_fetcher,
        "ensure_login_detailed",
        lambda _tab: SimpleNamespace(
            ok=False,
            reason="profile_missing_login",
            check=SimpleNamespace(page_state="login_required", current_url="https://x.com/home"),
        ),
    )

    with pytest.raises(ChallengeSignal) as exc:
        reply_fetcher._ensure_reply_session_ready(tab, task_id="task-login", browser_instance=None)

    assert exc.value.risk_state == "login_required"


def test_reply_fetcher_primes_x_domain_before_quick_login_check(monkeypatch):
    from crawler import reply_fetcher

    call_order: list[str] = []

    monkeypatch.setattr(
        reply_fetcher,
        "ensure_x_domain_context",
        lambda _tab: call_order.append("prime"),
    )
    monkeypatch.setattr(
        reply_fetcher,
        "check_login",
        lambda _tab: call_order.append("check") or True,
    )

    reply_fetcher._ensure_reply_session_ready(object(), task_id="task-prime", browser_instance=None)

    assert call_order == ["prime", "check"]


def test_reply_fetcher_batch_skips_do_not_open_shared_blank_tab(monkeypatch):
    from crawler import reply_fetcher

    browser_instance = _DummyBrowserInstance([])

    monkeypatch.setattr(reply_fetcher, "check_signal", lambda _task_id: None)

    tweets = [
        {
            "id": "tweet-1",
            "author": {"screen_name": "alice"},
            "metrics": {"replies": 0},
            "replies": [],
        }
    ]

    updated, failed = reply_fetcher.fetch_replies_batch(
        tweets=tweets,
        task_id="task-skip",
        browser_instance=browser_instance,
    )

    assert updated == tweets
    assert failed == []
    assert browser_instance.new_tab_calls == 0


def test_try_rotate_account_syncs_reply_browser_and_binds_task(monkeypatch):
    from crawler import x_searcher

    next_account = SimpleNamespace(
        account_id="acc-2",
        alias="@next",
        cookies=[{"name": "auth_token", "value": "token-2", "domain": ".x.com"}],
    )
    pool = SimpleNamespace(
        total_count=lambda: 2,
        pick_next_account=lambda current_id: next_account if current_id == "acc-1" else None,
    )
    current_account = SimpleNamespace(account_id="acc-1", alias="@current")
    reply_browser_instance = _DummyBrowserInstance([])
    bind_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(x_searcher, "ensure_login_with_pool", lambda _tab, _acc: True)
    monkeypatch.setattr(
        x_searcher._task_mgr,
        "bind_account",
        lambda task_id, account_id, alias: bind_calls.append((task_id, account_id, alias)),
    )

    rotated = x_searcher._try_rotate_account(
        tab=object(),
        current_account=current_account,
        pool=pool,
        reason="test",
        reply_browser_instance=reply_browser_instance,
        task_id="task-rotate",
    )

    assert rotated is next_account
    assert reply_browser_instance.synced == next_account.cookies
    assert bind_calls == [("task-rotate", "acc-2", "@next")]
    assert reply_browser_instance.bound_account_id == "acc-2"


def test_try_inject_pool_account_cookies_prefers_browser_bound_account(monkeypatch):
    from crawler import reply_fetcher

    account = SimpleNamespace(account_id="acc-1", alias="@bound")
    browser_instance = _DummyBrowserInstance([])
    browser_instance.bound_account_id = "acc-1"
    browser_instance.bound_account_alias = "@bound"

    fake_pool = SimpleNamespace(
        get_active_account_count=lambda: 2,
        get_account=lambda account_id: account if account_id == "acc-1" else None,
        pick_next_account=lambda: pytest.fail("实例已绑定账号时不应回退到其他账号"),
    )

    monkeypatch.setattr("crawler.account_pool.get_pool", lambda: fake_pool)
    monkeypatch.setattr("api.services.task_manager.get_task_account", lambda _task_id: (None, None))
    monkeypatch.setattr(
        "crawler.auth.ensure_login_with_pool_detailed",
        lambda _tab, picked: SimpleNamespace(ok=True, reason="ok") if picked is account else pytest.fail("应使用绑定账号"),
    )

    assert reply_fetcher._try_inject_pool_account_cookies(object(), "task-1", browser_instance=browser_instance) is True


def test_safe_stop_listener_ignores_missing_driver():
    from crawler import reply_fetcher

    tab = SimpleNamespace(listen=SimpleNamespace(_driver=None, stop=lambda: pytest.fail("不应调用 stop")))

    reply_fetcher._safe_stop_listener(tab)
