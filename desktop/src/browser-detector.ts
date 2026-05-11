/**
 * 检测系统是否安装了 Chromium 内核浏览器（DrissionPage 强依赖）。
 * 找不到时桌面端会引导用户安装。
 */
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

export interface BrowserInfo {
  name: string;
  path: string;
}

function existing(candidates: string[]): string | null {
  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) return p;
    } catch {
      /* ignore */
    }
  }
  return null;
}

export function detectBrowser(): BrowserInfo | null {
  if (process.platform === "darwin") {
    const candidates = [
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
      "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ];
    const hit = existing(candidates);
    if (!hit) return null;
    return { name: path.basename(hit), path: hit };
  }

  if (process.platform === "win32") {
    const pf = process.env["ProgramFiles"] ?? "C:\\Program Files";
    const pf86 = process.env["ProgramFiles(x86)"] ?? "C:\\Program Files (x86)";
    const localAppData =
      process.env["LOCALAPPDATA"] ?? path.join(os.homedir(), "AppData", "Local");
    const candidates = [
      path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
      path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
      path.join(localAppData, "Google", "Chrome", "Application", "chrome.exe"),
      path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
      path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
    ];
    const hit = existing(candidates);
    if (!hit) return null;
    return { name: path.basename(hit), path: hit };
  }

  // linux
  const candidates = [
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
  ];
  const hit = existing(candidates);
  if (!hit) return null;
  return { name: path.basename(hit), path: hit };
}
