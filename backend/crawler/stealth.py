"""浏览器深度伪装注入（增强模式 v2）。

覆盖主流反自动化检测点：
  1) navigator.webdriver → undefined
  2) window.chrome 完整运行时（含 csi / loadTimes）
  3) navigator.plugins 补全（PDF Viewer 等常见插件）
  4) WebGL 渲染器/厂商伪装（避免 SwiftShader 特征）
  5) navigator.permissions.query 修补
  6) 无头模式窗口尺寸修正（outerWidth/outerHeight）
  7) 移除 CDP Runtime.enable 注入的 sourceurl 标记
  8) navigator.languages / connection 保底
  9) navigator/screen/userAgentData 完整属性覆盖（macOS + Edge 145 档案）
 10) Canvas + AudioContext + WebGL readPixels 指纹噪声
"""
from __future__ import annotations

import logging

from crawler.stealth_canvas import CANVAS_AUDIO_STEALTH_SCRIPT
from crawler.stealth_navigator import NAVIGATOR_STEALTH_SCRIPT

logger = logging.getLogger(__name__)

_CORE_SCRIPT = r"""
(() => {
  // ── 1. navigator.webdriver ──────────────────────────────────────
  try {
    Object.defineProperty(navigator, 'webdriver', {
      get: () => undefined,
      configurable: true,
    });
  } catch (_) {}

  // ── 2. window.chrome 完整运行时 ────────────────────────────────
  try {
    if (!window.chrome || !window.chrome.runtime) {
      const chromeObj = {
        runtime: {
          onMessage: { addListener() {}, removeListener() {} },
          onConnect: { addListener() {}, removeListener() {} },
          sendMessage() {},
          connect() { return { onMessage: { addListener() {} }, postMessage() {} }; },
          PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
          PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64', MIPS: 'mips', MIPS64: 'mips64' },
        },
        csi() { return { startE: Date.now(), onloadT: Date.now() + 280, pageT: Date.now() + 280, tran: 15 }; },
        loadTimes() {
          const now = Date.now() / 1000;
          return {
            commitLoadTime: now, connectionInfo: 'h2',
            finishDocumentLoadTime: now + 0.3, finishLoadTime: now + 0.5,
            firstPaintAfterLoadTime: 0, firstPaintTime: now + 0.15,
            navigationType: 'Other', npnNegotiatedProtocol: 'h2',
            requestTime: now - 0.8, startLoadTime: now - 0.5,
            wasAlternateProtocolAvailable: false, wasFetchedViaSpdy: true, wasNpnNegotiated: true,
          };
        },
      };
      Object.defineProperty(window, 'chrome', {
        get: () => chromeObj,
        configurable: true,
      });
    }
  } catch (_) {}

  // ── 3. navigator.plugins 补全 ──────────────────────────────────
  try {
    if (navigator.plugins.length === 0) {
      const mkMime = (type, suffixes, desc, plugin) => {
        const m = Object.create(MimeType.prototype);
        Object.defineProperties(m, {
          type:          { get: () => type },
          suffixes:      { get: () => suffixes },
          description:   { get: () => desc },
          enabledPlugin: { get: () => plugin },
        });
        return m;
      };
      const mkPlugin = (name, desc, fn, mimes) => {
        const p = Object.create(Plugin.prototype);
        const ms = mimes.map(([t, s, d]) => mkMime(t, s, d, p));
        Object.defineProperties(p, {
          name:        { get: () => name },
          description: { get: () => desc },
          filename:    { get: () => fn },
          length:      { get: () => ms.length },
        });
        ms.forEach((m, i) => {
          Object.defineProperty(p, i, { get: () => m });
          Object.defineProperty(p, m.type, { get: () => m });
        });
        p[Symbol.iterator] = function*() { yield* ms; };
        return p;
      };
      const pdfMimes = [['application/pdf','pdf','Portable Document Format'],['text/pdf','pdf','Portable Document Format']];
      const plugins = [
        mkPlugin('PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
        mkPlugin('Chrome PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
        mkPlugin('Chromium PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
        mkPlugin('Microsoft Edge PDF Viewer', '', 'internal-pdf-viewer', [['application/pdf','pdf','']]),
        mkPlugin('WebKit built-in PDF', '', 'internal-pdf-viewer', [['application/pdf','pdf','']]),
      ];
      Object.defineProperty(Navigator.prototype, 'plugins', {
        get: () => {
          const arr = Object.create(PluginArray.prototype);
          plugins.forEach((p, i) => {
            Object.defineProperty(arr, i, { get: () => p, enumerable: true });
            Object.defineProperty(arr, p.name, { get: () => p });
          });
          Object.defineProperty(arr, 'length', { get: () => plugins.length });
          arr[Symbol.iterator] = function*() { yield* plugins; };
          arr.item = (i) => plugins[i] || null;
          arr.namedItem = (n) => plugins.find(p => p.name === n) || null;
          arr.refresh = () => {};
          return arr;
        },
        configurable: true,
      });
    }
  } catch (_) {}

  // ── 4. WebGL 渲染器伪装（避免 SwiftShader 暴露） ───────────────
  try {
    const patchGL = (proto) => {
      const orig = proto.getParameter;
      proto.getParameter = function(p) {
        if (p === 37445) return 'Google Inc. (NVIDIA)';
        if (p === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)';
        return orig.call(this, p);
      };
    };
    patchGL(WebGLRenderingContext.prototype);
    if (typeof WebGL2RenderingContext !== 'undefined') patchGL(WebGL2RenderingContext.prototype);
  } catch (_) {}

  // ── 5. permissions.query 修补 ──────────────────────────────────
  try {
    const oq = navigator.permissions && navigator.permissions.query;
    if (typeof oq === 'function') {
      navigator.permissions.query = (p) => (
        p && p.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission })
          : oq.call(navigator.permissions, p)
      );
    }
  } catch (_) {}

  // ── 6. 无头模式窗口尺寸修正 ────────────────────────────────────
  try {
    if (window.outerWidth === 0 || window.outerHeight === 0) {
      Object.defineProperty(window, 'outerWidth',  { get: () => window.innerWidth  || 1366 });
      Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight || 860 });
    }
    if (window.screenX === 0 && window.screenY === 0) {
      Object.defineProperty(window, 'screenX', { get: () => 13 });
      Object.defineProperty(window, 'screenY', { get: () => 58 });
    }
  } catch (_) {}

  // ── 7. 移除 sourceURL 泄露 ────────────────────────────────────
  try {
    const ots = Function.prototype.toString;
    Function.prototype.toString = function() {
      return ots.call(this).replace(/\n\/\/# sourceURL=.*$/gm, '');
    };
  } catch (_) {}

  // ── 8. navigator.languages 保底 ───────────────────────────────
  try {
    if (!navigator.languages || navigator.languages.length === 0) {
      Object.defineProperty(Navigator.prototype, 'languages', {
        get: () => ['zh-CN', 'zh', 'en', 'en-GB', 'en-US'],
        configurable: true,
      });
    }
  } catch (_) {}

  // ── 9. navigator.connection 补全 ──────────────────────────────
  try {
    if (!navigator.connection) {
      Object.defineProperty(Navigator.prototype, 'connection', {
        get: () => ({
          effectiveType: '4g', rtt: 50, downlink: 10, saveData: false,
          onchange: null, addEventListener() {}, removeEventListener() {},
        }),
        configurable: true,
      });
    }
  } catch (_) {}
})();
""".strip()

# 合并所有子模块脚本：核心 → navigator/screen/userAgentData → Canvas/Audio/WebGL 噪声
_STEALTH_INIT_SCRIPT = "\n\n".join([
    _CORE_SCRIPT,
    NAVIGATOR_STEALTH_SCRIPT,
    CANVAS_AUDIO_STEALTH_SCRIPT,
])


def apply_stealth_to_tab(tab, *, enabled: bool) -> bool:
    """将反检测脚本注入到标签页初始化脚本中。

    脚本会在每次页面导航时自动执行（在页面 JS 之前）。
    """
    if not enabled:
        return False
    try:
        tab.add_init_js(_STEALTH_INIT_SCRIPT)
        return True
    except Exception as e:
        logger.warning(f"Stealth 初始化脚本注入失败（忽略继续）: {e}")
        return False
