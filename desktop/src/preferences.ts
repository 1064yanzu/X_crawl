/**
 * 桌面端用户偏好（独立于后端 settings）—— 退出确认、通知开关、窗口记忆。
 *
 * 后端 settings 关注爬虫行为；这些偏好只影响桌面壳行为，保留在用户数据目录的独立 JSON。
 */
import fs from "node:fs";
import path from "node:path";
import { app } from "electron";

export interface DesktopPreferences {
    notifyOnTaskDone: boolean;
    confirmOnQuit: "always" | "if-active" | "never";
    rememberWindowState: boolean;
}

const DEFAULTS: DesktopPreferences = {
    notifyOnTaskDone: true,
    confirmOnQuit: "if-active",
    rememberWindowState: true,
};

const FILE_NAME = "desktop-preferences.json";

function prefsPath(): string {
    return path.join(app.getPath("userData"), FILE_NAME);
}

let cache: DesktopPreferences | null = null;

export function getPreferences(): DesktopPreferences {
    if (cache) return cache;
    try {
        const fp = prefsPath();
        if (fs.existsSync(fp)) {
            const parsed = JSON.parse(fs.readFileSync(fp, "utf-8")) as Partial<DesktopPreferences>;
            cache = { ...DEFAULTS, ...parsed };
            return cache;
        }
    } catch {
        /* ignore */
    }
    cache = { ...DEFAULTS };
    return cache;
}

export function setPreferences(patch: Partial<DesktopPreferences>): DesktopPreferences {
    const next = { ...getPreferences(), ...patch };
    // 校验 confirmOnQuit
    if (!["always", "if-active", "never"].includes(next.confirmOnQuit)) {
        next.confirmOnQuit = DEFAULTS.confirmOnQuit;
    }
    cache = next;
    try {
        fs.writeFileSync(prefsPath(), JSON.stringify(next, null, 2), "utf-8");
    } catch {
        /* ignore */
    }
    return next;
}
