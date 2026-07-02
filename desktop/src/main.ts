import { app, BrowserWindow, dialog, ipcMain, Menu, session, shell } from "electron";
import path from "node:path";
import { request as httpRequest } from "node:http";
import {
    ensureDataDir,
    ensureDesktopLogDir,
    desktopLogDir,
    dataDir,
} from "./paths";
import { pickPort } from "./port";
import { startBackend, startFrontend, stopAll } from "./runner";
import { detectBrowser } from "./browser-detector";
import { loadWindowState, trackWindow, resetWindowState } from "./window-state";
import { buildAppMenu } from "./menu";
import { mapStartupError } from "./error-mapper";
import { startNotifications, stopNotifications } from "./notifications";
import { getPreferences, setPreferences } from "./preferences";

// 防止多开
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
    app.quit();
    process.exit(0);
}

let splashWin: BrowserWindow | null = null;
let mainWin: BrowserWindow | null = null;
let firstRunWin: BrowserWindow | null = null;
let backendPort: number | null = null;
let frontendPort: number | null = null;
let quitConfirmed = false;

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
            preload: path.join(__dirname, "preload-splash.js"),
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
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
            preload: path.join(__dirname, "preload-first-run.js"),
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
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

// ─── IPC：暴露给前端的安全 API ────────────────────────────────────────────
ipcMain.handle("xcrawl:open-external", async (_e, url: string) => {
    if (typeof url !== "string") return false;
    // 仅放行 http(s) / mailto
    if (!/^(https?:\/\/|mailto:)/i.test(url)) return false;
    await shell.openExternal(url);
    return true;
});

ipcMain.handle("xcrawl:open-log-dir", async () => {
    await shell.openPath(desktopLogDir);
    return true;
});

ipcMain.handle("xcrawl:open-data-dir", async () => {
    await shell.openPath(dataDir);
    return true;
});

ipcMain.handle("xcrawl:active-tasks", async () => {
    return queryActiveTasksCount();
});

ipcMain.handle(
    "xcrawl:notify",
    async (_e, payload: { taskId: string; title: string; body?: string }) => {
        const { Notification } = await import("electron");
        if (!Notification.isSupported()) return false;
        const n = new Notification({
            title: payload.title || "X_crawl",
            body: payload.body || "任务有新进展",
            silent: false,
        });
        n.on("click", () => focusMainWin());
        n.show();
        return true;
    },
);

ipcMain.handle("xcrawl:runtime-info", async () => ({
    version: app.getVersion(),
    platform: process.platform,
    dataDir,
    logDir: desktopLogDir,
    backendPort,
}));

ipcMain.handle("xcrawl:reset-window", async () => {
    resetWindowState();
    if (mainWin) {
        mainWin.setSize(1440, 900);
        mainWin.center();
    }
    return true;
});

ipcMain.handle("xcrawl:get-preferences", async () => getPreferences());
ipcMain.handle("xcrawl:set-preferences", async (_e, patch) => setPreferences(patch || {}));

// ─── 启动 ──────────────────────────────────────────────────────────────────
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
        backendPort = await pickPort();
        frontendPort = await pickPort();

        setStatus("正在启动后端服务...");
        await startBackend(backendPort);

        setStatus("正在启动前端界面...");
        await startFrontend(frontendPort, backendPort);

        setStatus("即将就绪...");
        await openMain(frontendPort);

        // 主窗口起来后启动任务完成通知守护
        startNotifications({
            getBackendPort: () => backendPort,
            getMainWin: () => mainWin,
            getPreferences: () => ({ notifyOnTaskDone: getPreferences().notifyOnTaskDone }),
        });
    } catch (e) {
        splashWin?.close();
        splashWin = null;
        const mapped = mapStartupError(e);
        const choice = await dialog.showMessageBox({
            type: "error",
            title: mapped.title,
            message: mapped.message,
            detail: mapped.detail,
            buttons: ["打开日志目录", "退出"],
            defaultId: 0,
            cancelId: 1,
        });
        if (choice.response === 0) {
            await shell.openPath(desktopLogDir);
        }
        quitConfirmed = true;
        app.quit();
    }
}

async function openMain(port: number): Promise<void> {
    const prefs = getPreferences();
    const saved = prefs.rememberWindowState
        ? loadWindowState({ defaultWidth: 1440, defaultHeight: 900, minWidth: 1100, minHeight: 720 })
        : { width: 1440, height: 900 };

    mainWin = new BrowserWindow({
        x: saved.x,
        y: saved.y,
        width: saved.width,
        height: saved.height,
        minWidth: 1100,
        minHeight: 720,
        show: false,
        backgroundColor: "#fafafa",
        title: "X_crawl",
        webPreferences: {
            preload: path.join(__dirname, "preload.js"),
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
        },
    });

    if (saved.isMaximized) mainWin.maximize();

    // CSP 兜底：除了 layout meta，再在响应头层面注入一份
    session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
        callback({
            responseHeaders: {
                ...details.responseHeaders,
                "Content-Security-Policy": [
                    [
                        "default-src 'self' http://127.0.0.1:*",
                        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
                        "style-src 'self' 'unsafe-inline'",
                        "img-src 'self' data: blob: https://*.twimg.com https://*.x.com https://*.youtube.com https://yt3.ggpht.com",
                        "media-src 'self' blob: https://*.twimg.com",
                        "connect-src 'self' http://127.0.0.1:* http://localhost:*",
                        "font-src 'self' data:",
                        "frame-src 'none'",
                    ].join("; "),
                ],
            },
        });
    });

    await mainWin.loadURL(`http://127.0.0.1:${port}/`);

    // 等真正渲染好再显示，避免白屏闪烁
    mainWin.once("ready-to-show", () => {
        if (!mainWin) return;
        mainWin.show();
        splashWin?.close();
        splashWin = null;
    });

    if (prefs.rememberWindowState) {
        trackWindow(mainWin, "main");
    }

    // 阻止应用窗口内导航到外部站点
    mainWin.webContents.setWindowOpenHandler(({ url }) => {
        if (url.startsWith("http://127.0.0.1:") || url.startsWith("http://localhost:")) {
            return { action: "allow" };
        }
        shell.openExternal(url);
        return { action: "deny" };
    });

    mainWin.on("closed", () => {
        mainWin = null;
    });

    // 挂载中文菜单
    Menu.setApplicationMenu(
        buildAppMenu({
            onOpenLogDir: () => shell.openPath(desktopLogDir),
            onOpenDataDir: () => shell.openPath(dataDir),
            onResetWindow: () => {
                resetWindowState();
                if (mainWin) {
                    mainWin.setSize(1440, 900);
                    mainWin.center();
                }
            },
        }),
    );
}

function focusMainWin() {
    if (mainWin) {
        if (mainWin.isMinimized()) mainWin.restore();
        mainWin.show();
        mainWin.focus();
    }
}

// ─── 退出确认 ──────────────────────────────────────────────────────────────
function queryActiveTasksCount(): Promise<number> {
    return new Promise((resolve) => {
        if (!backendPort) return resolve(0);
        const req = httpRequest(
            {
                hostname: "127.0.0.1",
                port: backendPort,
                path: "/api/v1/tasks?include_payload=false",
                method: "GET",
                timeout: 3000,
            },
            (res) => {
                let chunks = "";
                res.on("data", (c) => (chunks += c));
                res.on("end", () => {
                    try {
                        const parsed = JSON.parse(chunks);
                        if (!Array.isArray(parsed)) return resolve(0);
                        const active = parsed.filter(
                            (t: { status: string }) =>
                                t.status === "running" || t.status === "paused" || t.status === "pending",
                        );
                        resolve(active.length);
                    } catch {
                        resolve(0);
                    }
                });
            },
        );
        req.on("error", () => resolve(0));
        req.on("timeout", () => {
            req.destroy();
            resolve(0);
        });
        req.end();
    });
}

async function pauseAllTasks(): Promise<void> {
    if (!backendPort) return;
    await new Promise<void>((resolve) => {
        const req = httpRequest(
            {
                hostname: "127.0.0.1",
                port: backendPort,
                path: "/api/v1/tasks/pause-all",
                method: "POST",
                timeout: 8000,
            },
            (res) => {
                res.on("data", () => {});
                res.on("end", () => resolve());
            },
        );
        req.on("error", () => resolve());
        req.on("timeout", () => {
            req.destroy();
            resolve();
        });
        req.end();
    });
}

async function confirmAndQuit(): Promise<"proceed" | "cancel"> {
    const prefs = getPreferences();
    if (prefs.confirmOnQuit === "never") return "proceed";

    const active = await queryActiveTasksCount();
    if (prefs.confirmOnQuit === "if-active" && active === 0) return "proceed";

    const choice = await dialog.showMessageBox({
        type: "question",
        title: "退出 X_crawl",
        message:
            active > 0
                ? `当前有 ${active} 个任务在运行 / 暂停 / 排队，确定要退出吗？`
                : "确定要退出 X_crawl 吗？",
        detail: active > 0
            ? "退出后任务会停在断点，下次启动可在任务中心点击继续。"
            : "",
        buttons: active > 0 ? ["暂停后退出", "直接退出", "取消"] : ["退出", "取消"],
        defaultId: 0,
        cancelId: active > 0 ? 2 : 1,
    });

    if (active > 0) {
        if (choice.response === 0) {
            await pauseAllTasks();
            return "proceed";
        } else if (choice.response === 1) {
            return "proceed";
        } else {
            return "cancel";
        }
    } else {
        return choice.response === 0 ? "proceed" : "cancel";
    }
}

app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
        app.quit();
    }
});

app.on("before-quit", async (event) => {
    if (quitConfirmed) return;  // 已确认，放行 stopAll 由后续 hook 完成
    event.preventDefault();
    const decision = await confirmAndQuit();
    if (decision === "cancel") return;
    quitConfirmed = true;
    try {
        stopNotifications();
        await stopAll();
    } catch (e) {
        console.error("[stopAll] failed", e);
    }
    app.exit(0);
});

app.on("activate", () => {
    if (mainWin) {
        focusMainWin();
        return;
    }
    if (frontendPort) {
        // 后端/前端仍在运行，只是窗口被关，重新打开主窗口
        void openMain(frontendPort);
    } else {
        // 整个服务都没起来（比如启动失败后保留了 dock 图标），重新 boot
        void boot();
    }
});

app.on("second-instance", () => {
    focusMainWin();
});

app.whenReady().then(() => {
    boot();
});
