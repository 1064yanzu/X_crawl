from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _CookieTimeoutTab:
    def __init__(self) -> None:
        self.calls = 0

    def cookies(self):
        self.calls += 1
        if self.calls == 1:
            return [
                {"name": "auth_token", "value": "token"},
                {"name": "twid", "value": "u%3D123"},
            ]
        raise TimeoutError("timeout | method=Network.getCookies")


def test_get_cookie_dict_falls_back_to_recent_cache_on_timeout():
    from crawler import auth

    tab = _CookieTimeoutTab()

    first = auth._get_cookie_dict(tab)
    second = auth._get_cookie_dict(tab)

    assert first == {"auth_token": "token", "twid": "u%3D123"}
    assert second == first


def test_get_cookie_dict_returns_empty_without_cache_on_timeout():
    from crawler import auth

    # 清除前一个测试留下的缓存
    with auth._cookie_cache_lock:
        auth._cookie_cache.clear()

    class _AlwaysTimeoutTab:
        def cookies(self):
            raise TimeoutError("timeout | method=Network.getCookies")

    assert auth._get_cookie_dict(_AlwaysTimeoutTab()) == {}
