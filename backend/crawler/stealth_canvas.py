"""Canvas / WebGL / AudioContext 指纹噪声注入模块。

为每个页面会话生成固定的 LCG 伪随机种子，对以下三类浏览器指纹
采集接口注入微量噪声，使每次采集结果产生不可预测的细微差异，
从而有效干扰跨站指纹追踪：

  1) Canvas 2D — toDataURL / toBlob 输出像素噪声
  2) WebGL — readPixels 最低位翻转
  3) AudioContext — oscillator 频率 & gain 增益微扰
"""
from __future__ import annotations

CANVAS_AUDIO_STEALTH_SCRIPT: str = r"""
(() => {
  // ── 页面级固定 LCG 伪随机种子 ───────────────────────────────────
  try {
    let _s = (Math.random() * 2147483647) | 0;
    const _seed = () => {
      _s = (Math.imul(1664525, _s) + 1013904223) | 0;
      return (_s >>> 0) / 4294967296;
    };

    // ── 1. Canvas 2D 指纹噪声 ────────────────────────────────────
    try {
      const _addNoise = (canvas) => {
        try {
          const w = canvas.width;
          const h = canvas.height;
          if (w * h > 65536) return;
          const ctx = canvas.getContext('2d');
          if (!ctx) return;
          const imageData = ctx.getImageData(0, 0, w, h);
          const data = imageData.data;
          const len = data.length;
          for (let i = 0; i < len; i += 4) {
            if (_seed() < 0.02) {
              data[i]     = Math.max(0, Math.min(255, data[i]     + (_seed() < 0.5 ? -1 : 1)));
              data[i + 1] = Math.max(0, Math.min(255, data[i + 1] + (_seed() < 0.5 ? -1 : 1)));
              data[i + 2] = Math.max(0, Math.min(255, data[i + 2] + (_seed() < 0.5 ? -1 : 1)));
            }
          }
          ctx.putImageData(imageData, 0, 0);
        } catch (_) {}
      };

      const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
      HTMLCanvasElement.prototype.toDataURL = function() {
        _addNoise(this);
        return _origToDataURL.apply(this, arguments);
      };

      const _origToBlob = HTMLCanvasElement.prototype.toBlob;
      HTMLCanvasElement.prototype.toBlob = function() {
        _addNoise(this);
        return _origToBlob.apply(this, arguments);
      };
    } catch (_) {}

    // ── 2. WebGL readPixels 噪声 ─────────────────────────────────
    try {
      const _patchReadPixels = (proto) => {
        const orig = proto.readPixels;
        proto.readPixels = function() {
          orig.apply(this, arguments);
          try {
            const pixels = arguments[6];
            if (pixels && pixels.length > 0) {
              const idx = ((_seed() * pixels.length) | 0) % pixels.length;
              pixels[idx] ^= 1;
            }
          } catch (_) {}
        };
      };
      _patchReadPixels(WebGLRenderingContext.prototype);
      if (typeof WebGL2RenderingContext !== 'undefined') {
        _patchReadPixels(WebGL2RenderingContext.prototype);
      }
    } catch (_) {}

    // ── 3. AudioContext 指纹噪声 ──────────────────────────────────
    try {
      const _patchAudioContext = (CtxClass) => {
        if (!CtxClass || !CtxClass.prototype) return;

        const origCreateOsc = CtxClass.prototype.createOscillator;
        CtxClass.prototype.createOscillator = function() {
          const osc = origCreateOsc.apply(this, arguments);
          try {
            osc.frequency.value += (_seed() - 0.5) * 0.02;
          } catch (_) {}
          return osc;
        };

        const origCreateGain = CtxClass.prototype.createGain;
        CtxClass.prototype.createGain = function() {
          const gain = origCreateGain.apply(this, arguments);
          try {
            gain.gain.value *= 1 + (_seed() - 0.5) * 0.0002;
          } catch (_) {}
          return gain;
        };
      };
      _patchAudioContext(window.AudioContext);
      _patchAudioContext(window.OfflineAudioContext);
    } catch (_) {}

  } catch (_) {}
})();
""".strip()
