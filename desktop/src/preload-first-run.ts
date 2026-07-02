/**
 * FirstRun 窗口 preload —— 暴露浏览器重试与外链打开 API。
 *
 * 注意：窗口启用了 sandbox，沙箱 preload 不能直接用 `shell`（仅暴露 ipcRenderer /
 * contextBridge 等子集），因此 openExternal 走主进程已注册的 `xcrawl:open-external`。
 */
import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("xcrawlFirstRun", {
    /** 通知主进程重新检测浏览器 */
    retryDetect(): void {
        ipcRenderer.send("first-run:retry");
    },
    /** 在系统浏览器打开外链（经主进程，沙箱安全） */
    openExternal(url: string): void {
        if (typeof url === "string" && /^https?:\/\//i.test(url)) {
            void ipcRenderer.invoke("xcrawl:open-external", url);
        }
    },
});
