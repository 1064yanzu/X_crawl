/**
 * 主窗口 preload —— 通过 contextBridge 暴露最小 IPC 给前端。
 *
 * 设计原则（Electron 2025 安全清单）：
 * - 主窗口启用 sandbox + contextIsolation，禁用 nodeIntegration
 * - preload 里只暴露受控的、白名单方法；不暴露 ipcRenderer 整体
 * - 前端通过 `window.xcrawl.*` 调用
 */
import { contextBridge, ipcRenderer } from "electron";

const api = {
    /** 探测是否运行在 Electron 桌面壳内（前端做 feature detect 用） */
    isDesktop: true,

    /** 在系统默认浏览器中打开外部链接 */
    openExternal(url: string): Promise<boolean> {
        if (!url || typeof url !== "string") return Promise.resolve(false);
        return ipcRenderer.invoke("xcrawl:open-external", url);
    },

    /** 打开桌面日志目录 */
    openLogDir(): Promise<boolean> {
        return ipcRenderer.invoke("xcrawl:open-log-dir");
    },

    /** 打开用户数据目录 */
    openDataDir(): Promise<boolean> {
        return ipcRenderer.invoke("xcrawl:open-data-dir");
    },

    /** 获取当前活跃任务数（用于退出确认） */
    getActiveTasksCount(): Promise<number> {
        return ipcRenderer.invoke("xcrawl:active-tasks");
    },

    /** 任务完成系统通知 */
    notifyTaskDone(payload: { taskId: string; title: string; body?: string }): Promise<boolean> {
        return ipcRenderer.invoke("xcrawl:notify", payload);
    },

    /** 桌面端运行时元信息 */
    getRuntimeInfo(): Promise<{
        version: string;
        platform: NodeJS.Platform;
        dataDir: string;
        logDir: string;
        backendPort: number | null;
    }> {
        return ipcRenderer.invoke("xcrawl:runtime-info");
    },

    /** 重置主窗口尺寸到默认值 */
    resetWindow(): Promise<boolean> {
        return ipcRenderer.invoke("xcrawl:reset-window");
    },

    /** 读取桌面端用户偏好 */
    getPreferences(): Promise<DesktopPreferences> {
        return ipcRenderer.invoke("xcrawl:get-preferences");
    },

    /** 写入桌面端用户偏好 */
    setPreferences(prefs: Partial<DesktopPreferences>): Promise<DesktopPreferences> {
        return ipcRenderer.invoke("xcrawl:set-preferences", prefs);
    },
};

export interface DesktopPreferences {
    notifyOnTaskDone: boolean;
    confirmOnQuit: "always" | "if-active" | "never";
    rememberWindowState: boolean;
}

declare global {
    // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
    interface Window {
        xcrawl: typeof api;
    }
}

contextBridge.exposeInMainWorld("xcrawl", api);
