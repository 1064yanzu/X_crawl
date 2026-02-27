from crawler.stealth import apply_stealth_to_tab


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
    assert "navigator, 'webdriver'" in tab.scripts[0]


def test_apply_stealth_disabled() -> None:
    tab = DummyTab()
    ok = apply_stealth_to_tab(tab, enabled=False)
    assert ok is False
    assert tab.scripts == []
