/**
 * Splash 窗口 preload —— 只暴露状态文本接收 API。
 *
 * Splash 关闭 nodeIntegration，所有 ipcRenderer.on 都走 preload。
 */
import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("xcrawlSplash", {
    onStatus(callback: (text: string) => void): () => void {
        const handler = (_e: Electron.IpcRendererEvent, text: string) => {
            try {
                callback(text);
            } catch {
                /* swallow */
            }
        };
        ipcRenderer.on("splash:status", handler);
        return () => ipcRenderer.off("splash:status", handler);
    },
});
