"""浏览器平衡档伪装注入。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_STEALTH_INIT_SCRIPT = r"""
// Basic stealth patches: keep behavior realistic, avoid aggressive spoofing.
Object.defineProperty(navigator, 'webdriver', {
  get: () => undefined,
});

Object.defineProperty(navigator, 'languages', {
  get: () => ['en-US', 'en'],
});

if (!window.chrome) {
  Object.defineProperty(window, 'chrome', {
    get: () => ({ runtime: {} }),
  });
}

if (!navigator.plugins || navigator.plugins.length === 0) {
  const fakePlugins = [
    { name: 'Chrome PDF Viewer' },
    { name: 'Chromium PDF Viewer' },
    { name: 'Microsoft Edge PDF Viewer' },
  ];
  Object.defineProperty(navigator, 'plugins', {
    get: () => fakePlugins,
  });
}

const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
  window.navigator.permissions.query = (parameters) => (
    parameters && parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters)
  );
}
""".strip()


def apply_stealth_to_tab(tab, *, enabled: bool) -> bool:
    if not enabled:
        return False
    try:
        tab.add_init_js(_STEALTH_INIT_SCRIPT)
        return True
    except Exception as e:
        logger.warning(f"Stealth 初始化脚本注入失败（忽略继续）: {e}")
        return False
