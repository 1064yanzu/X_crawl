from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_detect_preferred_browser_picks_first_compatible(monkeypatch):
    from crawler import browser_detector

    monkeypatch.setattr(
        browser_detector,
        "detect_all_browsers",
        lambda: [
            {
                "id": "firefox",
                "name": "Firefox",
                "engine": "firefox",
                "compatible": False,
                "path": "/Applications/Firefox.app/Contents/MacOS/firefox",
                "user_data_path": None,
            },
            {
                "id": "chrome",
                "name": "Google Chrome",
                "engine": "chromium",
                "compatible": True,
                "path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "user_data_path": "/Users/test/Library/Application Support/Google/Chrome",
            },
        ],
    )

    browser = browser_detector.detect_preferred_browser()

    assert browser is not None
    assert browser["id"] == "chrome"
    assert browser["user_data_path"] == "/Users/test/Library/Application Support/Google/Chrome"


def test_resolve_browser_paths_reuses_user_data_dir_when_enabled(monkeypatch):
    import config
    from crawler import browser

    monkeypatch.setattr(config.settings, "browser_exec_path", "", raising=False)
    monkeypatch.setattr(config.settings, "browser_user_data_path", "", raising=False)
    monkeypatch.setattr(config.settings, "browser_selected_id", "", raising=False)
    monkeypatch.setattr(config.settings, "browser_prefer_user_data_dir", True, raising=False)
    monkeypatch.setattr(
        browser,
        "detect_preferred_browser",
        lambda: {
            "id": "chrome",
            "name": "Google Chrome",
            "compatible": True,
            "path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "user_data_path": "/Users/test/Library/Application Support/Google/Chrome",
        },
    )

    exec_path, user_data_path = browser._resolve_browser_paths()

    assert exec_path == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    assert user_data_path == "/Users/test/Library/Application Support/Google/Chrome"


def test_resolve_browser_paths_can_disable_user_data_dir_preference(monkeypatch):
    import config
    from crawler import browser

    monkeypatch.setattr(config.settings, "browser_exec_path", "", raising=False)
    monkeypatch.setattr(config.settings, "browser_user_data_path", "", raising=False)
    monkeypatch.setattr(config.settings, "browser_selected_id", "", raising=False)
    monkeypatch.setattr(config.settings, "browser_prefer_user_data_dir", False, raising=False)
    monkeypatch.setattr(
        browser,
        "detect_preferred_browser",
        lambda: {
            "id": "chrome",
            "name": "Google Chrome",
            "compatible": True,
            "path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "user_data_path": "/Users/test/Library/Application Support/Google/Chrome",
        },
    )

    exec_path, user_data_path = browser._resolve_browser_paths()

    assert exec_path == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    assert user_data_path is None


def test_resolve_profile_directory_name_prefers_last_used_from_local_state(tmp_path):
    import json
    from crawler import browser

    user_data = tmp_path / "Chrome"
    user_data.mkdir()
    (user_data / "Default").mkdir()
    (user_data / "Profile 1").mkdir()
    (user_data / "Local State").write_text(
        json.dumps({"profile": {"last_used": "Profile 1"}}),
        encoding="utf-8",
    )

    profile_name = browser._resolve_profile_directory_name(str(user_data))

    assert profile_name == "Profile 1"


def test_resolve_profile_directory_name_falls_back_to_default(tmp_path):
    from crawler import browser

    user_data = tmp_path / "Chrome"
    user_data.mkdir()
    (user_data / "Default").mkdir()

    profile_name = browser._resolve_profile_directory_name(str(user_data))

    assert profile_name == "Default"


def test_create_browser_falls_back_to_crawler_profile_when_real_user_dir_launch_fails(monkeypatch, tmp_path):
    import config
    from crawler import browser

    real_user_data = tmp_path / "real-user-data"
    fallback_user_data = tmp_path / "crawler-profile"
    real_user_data.mkdir()
    fallback_user_data.mkdir()
    (real_user_data / "Default").mkdir()
    (fallback_user_data / "Default").mkdir()

    monkeypatch.setattr(config.settings, "browser_debug_port", 9222, raising=False)
    monkeypatch.setattr(config.settings, "browser_user_data_path", "", raising=False)
    monkeypatch.setattr(config.settings, "browser_exec_path", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", raising=False)
    monkeypatch.setattr(config.settings, "browser_selected_id", "", raising=False)
    monkeypatch.setattr(config.settings, "browser_prefer_user_data_dir", True, raising=False)
    monkeypatch.setattr(config.settings, "browser_proxy", "", raising=False)
    monkeypatch.setattr(config.settings, "browser_headless", False, raising=False)
    monkeypatch.setattr(config.settings, "browser_linux_hardening", False, raising=False)
    monkeypatch.setattr(config.settings, "browser_load_mode", "normal", raising=False)
    monkeypatch.setattr(browser, "_CRAWLER_PROFILE_DIR", str(fallback_user_data))
    monkeypatch.setattr(browser, "_is_port_open", lambda host, port: False)
    monkeypatch.setattr(browser, "_pick_free_local_port", lambda: 45678)
    monkeypatch.setattr(
        browser,
        "_resolve_browser_paths",
        lambda: ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", str(real_user_data)),
    )
    monkeypatch.setattr(browser, "_is_user_data_locked", lambda path: False)
    monkeypatch.setattr(browser, "_cleanup_stale_singleton_locks", lambda path: None)
    monkeypatch.setattr(browser, "_refresh_current_browser_pid", lambda: None)

    chromium_calls: list[str] = []

    class DummyChromiumOptions:
        def __init__(self):
            self.user_data_path = None

        def set_local_port(self, port):
            self.local_port = port

        def set_browser_path(self, path):
            self.browser_path = path

        def set_user_data_path(self, path):
            self.user_data_path = path

        def set_argument(self, *_args):
            return None

        def set_proxy(self, _proxy):
            return None

        def headless(self, _enabled):
            return None

        def set_load_mode(self, _mode):
            return None

        def mute(self, _enabled):
            return None

        def no_imgs(self, _enabled):
            return None

        def set_pref(self, *_args):
            return None

    class DummyBrowser:
        def __init__(self):
            self.set = self

        def timeouts(self, **_kwargs):
            return None

    def fake_chromium(co):
        chromium_calls.append(co.user_data_path)
        if co.user_data_path == str(real_user_data):
            raise RuntimeError("real profile launch failed")
        return DummyBrowser()

    monkeypatch.setattr(browser, "ChromiumOptions", DummyChromiumOptions)
    monkeypatch.setattr(browser, "Chromium", fake_chromium)

    launched = browser._create_browser()

    assert isinstance(launched, DummyBrowser)
    assert chromium_calls == [str(real_user_data), str(fallback_user_data)]
    assert browser.get_browser_session_info()["effective_user_data_path"] == str(fallback_user_data / "Default")
