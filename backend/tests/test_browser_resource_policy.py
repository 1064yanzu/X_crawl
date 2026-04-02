from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummySet:
    def __init__(self):
        self.blocked = "unset"

    def blocked_urls(self, urls):
        self.blocked = urls


class _DummyTab:
    def __init__(self):
        self.set = _DummySet()


class _DummyOptions:
    def __init__(self):
        self.no_imgs_value = None

    def no_imgs(self, value):
        self.no_imgs_value = value


def test_apply_browser_option_policies_uses_image_flag(monkeypatch):
    import config
    from crawler.browser_resource_policy import apply_browser_option_policies

    monkeypatch.setattr(config.settings, "browser_block_images", True, raising=False)
    options = _DummyOptions()

    apply_browser_option_policies(options)

    assert options.no_imgs_value is True


def test_apply_tab_resource_policies_blocks_video_urls(monkeypatch):
    import config
    from crawler.browser_resource_policy import apply_tab_resource_policies

    monkeypatch.setattr(config.settings, "browser_block_videos", True, raising=False)
    tab = _DummyTab()

    apply_tab_resource_policies(tab)

    assert isinstance(tab.set.blocked, list)
    assert any("video.twimg.com" in pattern for pattern in tab.set.blocked)


def test_apply_tab_resource_policies_clears_blocked_urls_when_disabled(monkeypatch):
    import config
    from crawler.browser_resource_policy import apply_tab_resource_policies

    monkeypatch.setattr(config.settings, "browser_block_videos", False, raising=False)
    tab = _DummyTab()

    apply_tab_resource_policies(tab)

    assert tab.set.blocked is None
