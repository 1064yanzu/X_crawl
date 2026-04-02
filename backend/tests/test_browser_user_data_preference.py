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
