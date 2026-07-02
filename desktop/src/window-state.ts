/**
 * 主窗口位置/大小记忆 —— 零依赖实现。
 *
 * 文件落在用户数据目录 / window-state.json，多窗口隔离按 key（默认 "main"）。
 * 启动时回放上次坐标，需校验屏幕仍存在；不存在则居中初始尺寸。
 */
import fs from "node:fs";
import path from "node:path";
import { app, screen, BrowserWindow, Rectangle } from "electron";

export interface WindowState {
    x?: number;
    y?: number;
    width: number;
    height: number;
    isMaximized?: boolean;
}

interface Options {
    key?: string;
    defaultWidth: number;
    defaultHeight: number;
    minWidth?: number;
    minHeight?: number;
}

const STORE_FILE = "window-state.json";

function loadStore(): Record<string, WindowState> {
    try {
        const fp = path.join(app.getPath("userData"), STORE_FILE);
        if (!fs.existsSync(fp)) return {};
        return JSON.parse(fs.readFileSync(fp, "utf-8")) || {};
    } catch {
        return {};
    }
}

function saveStore(store: Record<string, WindowState>): void {
    try {
        const fp = path.join(app.getPath("userData"), STORE_FILE);
        fs.writeFileSync(fp, JSON.stringify(store, null, 2), "utf-8");
    } catch {
        /* ignore — 窗口状态丢失不致命 */
    }
}

function isOnScreen(rect: Rectangle): boolean {
    const displays = screen.getAllDisplays();
    return displays.some((d) => {
        const b = d.workArea;
        return (
            rect.x + rect.width > b.x &&
            rect.x < b.x + b.width &&
            rect.y + rect.height > b.y &&
            rect.y < b.y + b.height
        );
    });
}

function clampToWorkArea(width: number, height: number): { width: number; height: number } {
    const work = screen.getPrimaryDisplay().workAreaSize;
    return {
        width: Math.min(width, Math.floor(work.width * 0.95)),
        height: Math.min(height, Math.floor(work.height * 0.95)),
    };
}

export function loadWindowState(opts: Options): WindowState {
    const key = opts.key ?? "main";
    const store = loadStore();
    const saved = store[key];

    if (saved && typeof saved.width === "number" && typeof saved.height === "number") {
        const rect: Rectangle = {
            x: saved.x ?? 0,
            y: saved.y ?? 0,
            width: saved.width,
            height: saved.height,
        };
        if (
            saved.x != null &&
            saved.y != null &&
            isOnScreen(rect) &&
            saved.width >= (opts.minWidth ?? 600) &&
            saved.height >= (opts.minHeight ?? 400)
        ) {
            return saved;
        }
    }

    // 首次启动 / 无效保存：用默认尺寸但夹到当前屏幕
    const clamped = clampToWorkArea(opts.defaultWidth, opts.defaultHeight);
    return clamped;
}

export function trackWindow(win: BrowserWindow, key = "main"): void {
    let writeTimer: NodeJS.Timeout | null = null;

    const persist = () => {
        if (writeTimer) clearTimeout(writeTimer);
        writeTimer = setTimeout(() => {
            try {
                const isMaximized = win.isMaximized();
                const b = isMaximized ? win.getNormalBounds() : win.getBounds();
                const store = loadStore();
                store[key] = {
                    x: b.x,
                    y: b.y,
                    width: b.width,
                    height: b.height,
                    isMaximized,
                };
                saveStore(store);
            } catch {
                /* ignore */
            }
        }, 400);
    };

    win.on("resize", persist);
    win.on("move", persist);
    win.on("maximize", persist);
    win.on("unmaximize", persist);
    win.on("close", () => {
        if (writeTimer) clearTimeout(writeTimer);
        persist();
    });
}

export function resetWindowState(key = "main"): void {
    const store = loadStore();
    delete store[key];
    saveStore(store);
}
