from types import SimpleNamespace

from crawler.packet_guard import wait_for_target_packet, is_search_timeline_body


class FakeListen:
    def __init__(self, packets):
        self._packets = list(packets)

    def wait(self, timeout=0, raise_err=False):
        if self._packets:
            return self._packets.pop(0)
        return None


class FakeTab:
    def __init__(self, packets):
        self.listen = FakeListen(packets)


class FakePacket:
    def __init__(self, body):
        self.response = SimpleNamespace(body=body)


def test_wait_for_target_packet_filters_irrelevant_packets():
    non_json = FakePacket("html")
    wrong_json = FakePacket({"data": {"foo": "bar"}})
    target = FakePacket({"data": {"search_by_raw_query": {"search_timeline": {}}}})
    tab = FakeTab([non_json, wrong_json, target])

    packet, ignored = wait_for_target_packet(
        tab,
        timeout=1.0,
        accept_body=is_search_timeline_body,
    )

    assert packet is target
    assert ignored == 2


def test_wait_for_target_packet_returns_none_after_timeout():
    tab = FakeTab([])
    packet, ignored = wait_for_target_packet(
        tab,
        timeout=0.3,
        accept_body=is_search_timeline_body,
    )
    assert packet is None
    assert ignored == 0
