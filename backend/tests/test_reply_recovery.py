import pytest

from crawler.crawl_signals import ChallengeSignal
from crawler.page_state import PageState
from crawler.recovery_policy import RecoveryPolicy
import crawler.reply_fetcher as reply_fetcher


class DummyListen:
    def stop(self):
        return None

    def start(self, _pattern):
        return None


class DummyTab:
    def __init__(self):
        self.listen = DummyListen()


def test_wait_reply_packet_quick_probe_hits(monkeypatch):
    tab = DummyTab()
    packet = object()
    calls = {"wait": 0, "soft": 0}

    def fake_wait_for_target_packet(*args, **kwargs):
        calls["wait"] += 1
        return packet, 0

    monkeypatch.setattr(reply_fetcher, "wait_for_target_packet", fake_wait_for_target_packet)
    monkeypatch.setattr(reply_fetcher, "soft_recover_for_packet", lambda *_args, **_kwargs: calls.__setitem__("soft", calls["soft"] + 1))

    got = reply_fetcher._wait_reply_packet_with_recovery(
        tab=tab,
        timeout=12.0,
        page_num=1,
        tweet_url="https://x.com/a/status/1",
        task_id="t1",
        policy=RecoveryPolicy(packet_soft_retries=2, refresh_max_retries=1, challenge_retry_times=1, challenge_cooldown=0.1),
    )

    assert got is packet
    assert calls["wait"] == 1
    assert calls["soft"] == 0


def test_wait_reply_packet_raises_challenge_signal(monkeypatch):
    tab = DummyTab()

    monkeypatch.setattr(reply_fetcher, "wait_for_target_packet", lambda *args, **kwargs: (None, 0))
    monkeypatch.setattr(reply_fetcher, "detect_page_state", lambda _tab: (PageState.CHALLENGE, "challenge"))
    monkeypatch.setattr(reply_fetcher, "sleep_with_jitter", lambda *args, **kwargs: None)

    with pytest.raises(ChallengeSignal):
        reply_fetcher._wait_reply_packet_with_recovery(
            tab=tab,
            timeout=0.5,
            page_num=1,
            tweet_url="https://x.com/a/status/1",
            task_id="t1",
            policy=RecoveryPolicy(packet_soft_retries=1, refresh_max_retries=1, challenge_retry_times=0, challenge_cooldown=0.1),
        )
