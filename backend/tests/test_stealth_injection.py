"""stealth.py 增强版测试：验证脚本注入和关键反检测覆盖点。"""
from crawler.stealth import apply_stealth_to_tab, _STEALTH_INIT_SCRIPT


class DummyTab:
    def __init__(self):
        self.scripts = []

    def add_init_js(self, script: str):
        self.scripts.append(script)
        return "sid-1"


def test_apply_stealth_enabled() -> None:
    tab = DummyTab()
    ok = apply_stealth_to_tab(tab, enabled=True)
    assert ok is True
    assert len(tab.scripts) == 1


def test_apply_stealth_disabled() -> None:
    tab = DummyTab()
    ok = apply_stealth_to_tab(tab, enabled=False)
    assert ok is False
    assert tab.scripts == []


def test_script_covers_webdriver() -> None:
    assert "navigator, 'webdriver'" in _STEALTH_INIT_SCRIPT


def test_script_covers_chrome_runtime() -> None:
    assert "chrome.csi" in _STEALTH_INIT_SCRIPT or "csi()" in _STEALTH_INIT_SCRIPT


def test_script_covers_plugins() -> None:
    assert "PDF Viewer" in _STEALTH_INIT_SCRIPT


def test_script_covers_webgl() -> None:
    assert "37446" in _STEALTH_INIT_SCRIPT  # UNMASKED_RENDERER_WEBGL
    assert "37445" in _STEALTH_INIT_SCRIPT  # UNMASKED_VENDOR_WEBGL


def test_script_covers_window_dimensions() -> None:
    assert "outerWidth" in _STEALTH_INIT_SCRIPT
    assert "outerHeight" in _STEALTH_INIT_SCRIPT


def test_script_covers_permissions() -> None:
    assert "permissions" in _STEALTH_INIT_SCRIPT


def test_script_covers_connection() -> None:
    assert "connection" in _STEALTH_INIT_SCRIPT


# ── 新覆盖点测试（v2 指纹增强） ───────────────────────────────────


def test_canvas_stealth_toDataURL() -> None:
    """Canvas 噪声脚本应包含 toDataURL 拦截"""
    from crawler.stealth_canvas import CANVAS_AUDIO_STEALTH_SCRIPT
    assert "toDataURL" in CANVAS_AUDIO_STEALTH_SCRIPT


def test_canvas_stealth_audio_context() -> None:
    """Audio 噪声脚本应处理 AudioContext 和 OfflineAudioContext"""
    from crawler.stealth_canvas import CANVAS_AUDIO_STEALTH_SCRIPT
    assert "AudioContext" in CANVAS_AUDIO_STEALTH_SCRIPT
    assert "OfflineAudioContext" in CANVAS_AUDIO_STEALTH_SCRIPT


def test_canvas_stealth_webgl_readpixels() -> None:
    """WebGL readPixels 应被拦截"""
    from crawler.stealth_canvas import CANVAS_AUDIO_STEALTH_SCRIPT
    assert "readPixels" in CANVAS_AUDIO_STEALTH_SCRIPT


def test_navigator_stealth_platform_macintel() -> None:
    """navigator.platform 应被设为 MacIntel"""
    from crawler.stealth_navigator import NAVIGATOR_STEALTH_SCRIPT
    assert "MacIntel" in NAVIGATOR_STEALTH_SCRIPT


def test_navigator_stealth_languages_zh_cn() -> None:
    """navigator.languages 应以 zh-CN 为优先"""
    from crawler.stealth_navigator import NAVIGATOR_STEALTH_SCRIPT
    assert "zh-CN" in NAVIGATOR_STEALTH_SCRIPT


def test_navigator_stealth_edge_brand() -> None:
    """userAgentData brands 应包含 Microsoft Edge 145"""
    from crawler.stealth_navigator import NAVIGATOR_STEALTH_SCRIPT
    assert "Microsoft Edge" in NAVIGATOR_STEALTH_SCRIPT
    assert "145" in NAVIGATOR_STEALTH_SCRIPT


def test_navigator_stealth_macos_platform() -> None:
    """userAgentData platform 应为 macOS"""
    from crawler.stealth_navigator import NAVIGATOR_STEALTH_SCRIPT
    assert "macOS" in NAVIGATOR_STEALTH_SCRIPT


def test_navigator_stealth_arm_architecture() -> None:
    """userAgentData architecture 应为 arm"""
    from crawler.stealth_navigator import NAVIGATOR_STEALTH_SCRIPT
    assert "arm" in NAVIGATOR_STEALTH_SCRIPT


def test_stealth_combined_includes_navigator() -> None:
    """合并后的 stealth 脚本应包含 MacIntel 和 zh-CN"""
    from crawler.stealth import _STEALTH_INIT_SCRIPT
    assert "MacIntel" in _STEALTH_INIT_SCRIPT
    assert "zh-CN" in _STEALTH_INIT_SCRIPT


def test_stealth_combined_includes_canvas() -> None:
    """合并后的 stealth 脚本应包含 Canvas 噪声"""
    from crawler.stealth import _STEALTH_INIT_SCRIPT
    assert "toDataURL" in _STEALTH_INIT_SCRIPT


def test_stealth_outerheight_860() -> None:
    """outerHeight 默认值应为 860（与 --window-size=1366,860 一致）"""
    from crawler.stealth import _STEALTH_INIT_SCRIPT
    assert "860" in _STEALTH_INIT_SCRIPT
