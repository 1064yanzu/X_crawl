import pytest

from crawler.crawl_signals import ChallengeSignal
from crawler.page_state import PageState
from crawler.recovery_policy import RecoveryPolicy
import crawler.x_searcher as x_searcher


class DummyListen:
    def stop(self):
        return None

    def start(self, _pattern):
        return None


class DummyTab:
    def __init__(self):
        self.listen = DummyListen()
        self.url = "https://x.com/search?q=test"


def test_wait_search_packet_soft_retry_then_success(monkeypatch):
    tab = DummyTab()
    packet = object()
    calls = {"wait": 0, "soft": 0}

    def fake_wait_for_target_packet(*args, **kwargs):
        calls["wait"] += 1
        if calls["wait"] == 1:
            return None, 0
        return packet, 0

    monkeypatch.setattr(x_searcher, "wait_for_target_packet", fake_wait_for_target_packet)
    monkeypatch.setattr(x_searcher, "detect_page_state", lambda _tab: (PageState.OK, "ok"))
    monkeypatch.setattr(x_searcher, "soft_recover_for_packet", lambda _tab, _attempt: calls.__setitem__("soft", calls["soft"] + 1))

    got = x_searcher._wait_search_packet_with_recovery(
        tab=tab,
        timeout=1.0,
        page_num=1,
        task_id="t1",
        policy=RecoveryPolicy(packet_soft_retries=2, refresh_max_retries=1, challenge_retry_times=1, challenge_cooldown=0.1),
    )

    assert got is packet
    assert calls["soft"] == 1


def test_wait_search_packet_raises_challenge_signal(monkeypatch):
    tab = DummyTab()
    monkeypatch.setattr(x_searcher, "wait_for_target_packet", lambda *args, **kwargs: (None, 0))
    monkeypatch.setattr(x_searcher, "detect_page_state", lambda _tab: (PageState.CHALLENGE, "challenge"))
    monkeypatch.setattr(x_searcher, "sleep_with_jitter", lambda *args, **kwargs: None)

    with pytest.raises(ChallengeSignal):
        x_searcher._wait_search_packet_with_recovery(
            tab=tab,
            timeout=0.5,
            page_num=2,
            task_id="t1",
            policy=RecoveryPolicy(packet_soft_retries=1, refresh_max_retries=1, challenge_retry_times=0, challenge_cooldown=0.1),
        )
