import { app, BrowserWindow, ipcMain, dialog, shell } from "electron";
import path from "node:path";
import fs from "node:fs";
import { ensureDataDir, ensureDesktopLogDir, desktopLogDir } from "./paths";
import { pickPort } from "./port";
import { startBackend, startFrontend, stopAll } from "./runner";
import { detectBrowser } from "./browser-detector";

// 防止多开
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
  process.exit(0);
}

let splashWin: BrowserWindow | null = null;
let mainWin: BrowserWindow | null = null;
let firstRunWin: BrowserWindow | null = null;

function setStatus(text: string): void {
  if (splashWin && !splashWin.isDestroyed()) {
    splashWin.webContents.send("splash:status", text);
  }
}

function createSplash(): void {
  splashWin = new BrowserWindow({
    width: 380,
    height: 320,
    frame: false,
    resizable: false,
    movable: true,
    transparent: false,
    show: false,
    backgroundColor: "#0c0d10",
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });
  splashWin.loadFile(path.join(__dirname, "..", "resources", "splash", "splash.html"));
  splashWin.once("ready-to-show", () => splashWin?.show());
}

function showFirstRun(): void {
  firstRunWin = new BrowserWindow({
    width: 600,
    height: 520,
    resizable: false,
    title: "需要安装浏览器",
    show: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });
  firstRunWin.loadFile(path.join(__dirname, "..", "resources", "splash", "first-run.html"));
  firstRunWin.once("ready-to-show", () => firstRunWin?.show());
}

ipcMain.on("first-run:retry", async () => {
  const detected = detectBrowser();
  if (detected) {
    firstRunWin?.close();
    firstRunWin = null;
    await boot();
  } else {
    dialog.showMessageBox({
      type: "warning",
      title: "未检测到浏览器",
      message: "仍未检测到 Chrome 或 Edge，请确认已正确安装。",
    });
  }
});

async function boot(): Promise<void> {
  ensureDataDir();
  ensureDesktopLogDir();

  // 1) Chrome 检查
  const browser = detectBrowser();
  if (!browser) {
    showFirstRun();
    return;
  }

  createSplash();

  try {
    setStatus("正在分配端口...");
    const backendPort = await pickPort();
    const frontendPort = await pickPort();

    setStatus("正在启动后端服务...");
    await startBackend(backendPort);

    setStatus("正在启动前端界面...");
    await startFrontend(frontendPort, backendPort);

    setStatus("即将就绪...");
    await openMain(frontendPort);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    splashWin?.close();
    const choice = await dialog.showMessageBox({
      type: "error",
      title: "启动失败",
      message: "X_crawl 启动失败",
      detail: msg + `\n\n日志目录：${desktopLogDir}`,
      buttons: ["打开日志目录", "退出"],
    });
    if (choice.response === 0) {
      shell.openPath(desktopLogDir);
    }
    app.quit();
  }
}

async function openMain(frontendPort: number): Promise<void> {
  mainWin = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    show: false,
    backgroundColor: "#fafafa",
    title: "X_crawl",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
    },
  });

  await mainWin.loadURL(`http://127.0.0.1:${frontendPort}/`);
  mainWin.show();
  splashWin?.close();
  splashWin = null;

  // 阻止应用窗口内的导航到外部站点 → 改用外部浏览器打开
  mainWin.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://127.0.0.1:") || url.startsWith("http://localhost:")) {
      return { action: "allow" };
    }
    shell.openExternal(url);
    return { action: "deny" };
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async (event) => {
  event.preventDefault();
  try {
    await stopAll();
  } catch (e) {
    console.error("[stopAll] failed", e);
  }
  // 解除 preventDefault 后再退出
  app.exit(0);
});

app.on("second-instance", () => {
  if (mainWin) {
    if (mainWin.isMinimized()) mainWin.restore();
    mainWin.focus();
  }
});

app.whenReady().then(() => {
  boot();
});
