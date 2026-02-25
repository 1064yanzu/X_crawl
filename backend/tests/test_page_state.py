from crawler.page_state import PageState, detect_page_state


class FakeTab:
    def __init__(self, html: str, url: str):
        self.html = html
        self.url = url


def test_detect_ok_page():
    tab = FakeTab("<html><body>normal timeline</body></html>", "https://x.com/home")
    state, _ = detect_page_state(tab)
    assert state == PageState.OK


def test_detect_challenge_page():
    tab = FakeTab("<html>Verify you are human before continuing</html>", "https://x.com/i/flow")
    state, _ = detect_page_state(tab)
    assert state == PageState.CHALLENGE


def test_detect_rate_limited_page():
    tab = FakeTab("<html>Rate limit exceeded, try again later.</html>", "https://x.com/search")
    state, _ = detect_page_state(tab)
    assert state == PageState.RATE_LIMITED


def test_detect_login_required_by_url():
    tab = FakeTab("<html>anything</html>", "https://x.com/i/flow/login")
    state, _ = detect_page_state(tab)
    assert state == PageState.LOGIN_REQUIRED


def test_detect_transient_error_page():
    tab = FakeTab("<html>Something went wrong. Try reloading.</html>", "https://x.com/search")
    state, _ = detect_page_state(tab)
    assert state == PageState.TRANSIENT_ERROR
