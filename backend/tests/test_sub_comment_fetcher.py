from crawler.weibo.sub_comment_fetcher import fetch_sub_comments


class _FakeResponse:
    def __init__(self, payload: dict):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


def test_fetch_sub_comments_not_limited_to_20_pages(monkeypatch):
    calls = {"count": 0}

    def _fake_get(_url, headers=None, timeout=None):
        calls["count"] += 1
        page = calls["count"]
        max_id = page if page < 25 else 0
        return _FakeResponse(
            {
                "ok": 1,
                "data": [{"id": f"c-{page}", "text": "x"}],
                "max_id": max_id,
            }
        )

    monkeypatch.setattr("crawler.weibo.sub_comment_fetcher.time.sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("config.settings.weibo_sub_comment_max_pages", 30, raising=False)

    class _Session:
        get = staticmethod(_fake_get)

    session = _Session()
    subs = fetch_sub_comments("cid-1", session=session, headers={}, page_interval=0)

    assert len(subs) == 25
    assert calls["count"] == 25
