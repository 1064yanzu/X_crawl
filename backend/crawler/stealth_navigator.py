"""Navigator / Screen / UserAgentData 属性覆盖模块。

伪装目标档案：macOS 10.15.7 + Microsoft Edge 145 + Apple Silicon arm64。

覆盖以下浏览器环境属性，使自动化浏览器呈现出与真实桌面
Edge 浏览器一致的指纹特征：

  1) navigator 核心属性（platform / UA / vendor / languages 等）
  2) navigator.userAgentData 完整 Client Hints 对象
  3) screen 尺寸与色深
  4) window.devicePixelRatio
"""
from __future__ import annotations

NAVIGATOR_STEALTH_SCRIPT: str = r"""
(() => {
  // ── 会话级随机参数（同一会话内固定） ─────────────────────────────
  try {
    const _colorDepth = Math.random() < 0.8 ? 30 : 24;
    const _hcPool = [8, 10, 12];
    const _hardwareConcurrency = _hcPool[(Math.random() * _hcPool.length) | 0];
    const _devicePixelRatio = Math.random() < 0.9 ? 2 : 1;

    const _UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0';

    // ── 1. navigator 属性覆盖 ────────────────────────────────────
    try {
      const _navProps = {
        platform: 'MacIntel',
        hardwareConcurrency: _hardwareConcurrency,
        deviceMemory: 8,
        userAgent: _UA,
        appVersion: _UA.replace('Mozilla/', ''),
        vendor: 'Google Inc.',
        maxTouchPoints: 0,
        languages: Object.freeze(['zh-CN', 'zh', 'en', 'en-GB', 'en-US']),
      };
      for (const [key, val] of Object.entries(_navProps)) {
        try {
          Object.defineProperty(Navigator.prototype, key, {
            get: () => val,
            configurable: true,
          });
        } catch (_) {}
      }
    } catch (_) {}

    // ── 2. navigator.userAgentData 覆盖 ──────────────────────────
    try {
      const _brands = [
        { brand: 'Not:A-Brand', version: '99' },
        { brand: 'Microsoft Edge', version: '145' },
        { brand: 'Chromium', version: '145' },
      ];
      const _uaData = {
        brands: _brands,
        mobile: false,
        platform: 'macOS',
        getHighEntropyValues: (hints) => Promise.resolve({
          architecture: 'arm',
          bitness: '64',
          brands: _brands,
          fullVersionList: [
            { brand: 'Not:A-Brand', version: '99.0.0.0' },
            { brand: 'Microsoft Edge', version: '145.0.3800.58' },
            { brand: 'Chromium', version: '145.0.7049.42' },
          ],
          mobile: false,
          model: '',
          platform: 'macOS',
          platformVersion: '26.3.0',
          uaFullVersion: '145.0.3800.58',
        }),
        toJSON: () => ({ brands: _brands, mobile: false, platform: 'macOS' }),
      };
      Object.defineProperty(Navigator.prototype, 'userAgentData', {
        get: () => _uaData,
        configurable: true,
      });
    } catch (_) {}

    // ── 3. screen 属性覆盖 ───────────────────────────────────────
    try {
      const _screenProps = {
        width: 2560,
        height: 1600,
        availWidth: 2560,
        availHeight: 1557,
        colorDepth: _colorDepth,
        pixelDepth: _colorDepth,
      };
      for (const [key, val] of Object.entries(_screenProps)) {
        try {
          Object.defineProperty(Screen.prototype, key, {
            get: () => val,
            configurable: true,
          });
        } catch (_) {}
      }
    } catch (_) {}

    // ── 4. window.devicePixelRatio 覆盖 ──────────────────────────
    try {
      Object.defineProperty(window, 'devicePixelRatio', {
        get: () => _devicePixelRatio,
        configurable: true,
      });
    } catch (_) {}

  } catch (_) {}
})();
""".strip()
