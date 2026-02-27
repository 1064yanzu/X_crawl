import crawler.browser as browser


class FakeOptions:
    def __init__(self):
        self.arguments = []
        self.headless_enabled = False
        self.load_mode = None
        self.user_data = None

    def set_local_port(self, _port):
        return self

    def set_browser_path(self, _path):
        return self

    def set_user_data_path(self, path):
        self.user_data = path
        return self

    def set_proxy(self, _proxy):
        return self

    def headless(self, enabled=True):
        self.headless_enabled = enabled
        return self

    def set_argument(self, key, value=None):
        self.arguments.append((key, value))
        return self

    def no_imgs(self, _flag):
        return self

    def set_load_mode(self, mode):
        self.load_mode = mode
        return self

    def mute(self, _flag):
        return self


def test_linux_headless_hardening_applied(monkeypatch):
    fake_co = FakeOptions()

    monkeypatch.setattr(browser, "_is_port_open", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(browser, "_resolve_browser_paths", lambda: (None, None))
    monkeypatch.setattr(browser, "_is_user_data_locked", lambda _path: False)
    monkeypatch.setattr(browser, "ChromiumOptions", lambda: fake_co)
    monkeypatch.setattr(browser, "Chromium", lambda _co: object())
    monkeypatch.setattr(browser, "should_force_headless_on_linux", lambda **_kwargs: True)
    monkeypatch.setattr(browser, "linux_headless_args_enabled", lambda **_kwargs: True)

    monkeypatch.setattr(browser.settings, "browser_user_data_path", "")
    monkeypatch.setattr(browser.settings, "browser_proxy", "")
    monkeypatch.setattr(browser.settings, "browser_block_images", False)
    monkeypatch.setattr(browser.settings, "browser_load_mode", "normal")
    monkeypatch.setattr(browser.settings, "browser_headless", False)
    monkeypatch.setattr(browser.settings, "browser_linux_hardening", True)

    browser._create_browser()

    assert fake_co.headless_enabled is True
    arg_keys = [a[0] for a in fake_co.arguments]
    assert "--no-sandbox" in arg_keys
    assert "--disable-dev-shm-usage" in arg_keys
    assert "--disable-gpu" in arg_keys
    assert "--disable-setuid-sandbox" in arg_keys
