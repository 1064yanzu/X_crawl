"""浏览器轻量伪装注入（保守模式）。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 说明：
# 1) 仅做最小化补丁，避免对页面运行时造成副作用；
# 2) 不再改写 navigator.plugins / navigator.languages，避免破坏站点脚本分支判断；
# 3) 若注入失败直接忽略，保证主流程可继续。
_STEALTH_INIT_SCRIPT = r"""
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', {
      get: () => undefined,
      configurable: true,
    });
  } catch (_) {}

  try {
    if (!window.chrome) {
      Object.defineProperty(window, 'chrome', {
        get: () => ({ runtime: {} }),
        configurable: true,
      });
    }
  } catch (_) {}

  try {
    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (typeof originalQuery === 'function') {
      window.navigator.permissions.query = (parameters) => (
        parameters && parameters.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission })
          : originalQuery(parameters)
      );
    }
  } catch (_) {}
})();
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
