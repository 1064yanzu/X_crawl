/**
 * 任务完成系统通知 —— 轮询 /api/v1/tasks 检测从 running/pending 到终态的迁移。
 *
 * 不走 SSE：SSE 按 task_id 一对一，订阅"所有任务"会复制大量状态；轮询 8s
 * 一次摘要（include_payload=false）开销极低。
 */
import { Notification, BrowserWindow } from "electron";
import { request as httpRequest } from "node:http";

interface TaskSnap {
    task_id: string;
    keyword: string;
    status: string;
    platform?: string;
}

let lastStatusByTaskId = new Map<string, string>();
let pollTimer: NodeJS.Timeout | null = null;
let stopped = false;
let getBackendPort: (() => number | null) | null = null;
let getMainWin: (() => BrowserWindow | null) | null = null;
let prefsGetter: (() => { notifyOnTaskDone: boolean }) | null = null;

const TERMINAL = new Set(["done", "failed", "stopped"]);
const POLL_MS = 8000;

function fetchTasks(port: number): Promise<TaskSnap[]> {
    return new Promise((resolve) => {
        const req = httpRequest(
            {
                hostname: "127.0.0.1",
                port,
                path: "/api/v1/tasks?include_payload=false",
                method: "GET",
                timeout: 5000,
            },
            (res) => {
                let chunks = "";
                res.on("data", (c) => (chunks += c));
                res.on("end", () => {
                    try {
                        const parsed = JSON.parse(chunks);
                        if (Array.isArray(parsed)) resolve(parsed as TaskSnap[]);
                        else resolve([]);
                    } catch {
                        resolve([]);
                    }
                });
            },
        );
        req.on("error", () => resolve([]));
        req.on("timeout", () => {
            req.destroy();
            resolve([]);
        });
        req.end();
    });
}

async function tick() {
    if (stopped) return;
    const port = getBackendPort?.() ?? null;
    if (!port) return;
    const tasks = await fetchTasks(port);
    const prefs = prefsGetter?.() ?? { notifyOnTaskDone: true };
    const nextStatus = new Map<string, string>();
    for (const t of tasks) {
        if (!t.task_id || !t.status) continue;
        nextStatus.set(t.task_id, t.status);
        const prev = lastStatusByTaskId.get(t.task_id);
        if (
            prefs.notifyOnTaskDone &&
            prev !== undefined &&
            !TERMINAL.has(prev) &&
            TERMINAL.has(t.status)
        ) {
            sendNotification(t);
        }
    }
    lastStatusByTaskId = nextStatus;
}

function sendNotification(t: TaskSnap) {
    if (!Notification.isSupported()) return;
    const titleMap: Record<string, string> = {
        done: "任务已完成",
        stopped: "任务已停止",
        failed: "任务执行失败",
    };
    const title = titleMap[t.status] || "任务状态更新";
    const body = `${t.platform?.toUpperCase() || "X"} · ${t.keyword || t.task_id.slice(0, 8)}`;
    const n = new Notification({ title, body, silent: false });
    n.on("click", () => {
        const win = getMainWin?.();
        if (win) {
            if (win.isMinimized()) win.restore();
            win.show();
            win.focus();
        }
    });
    n.show();
}

export function startNotifications(deps: {
    getBackendPort: () => number | null;
    getMainWin: () => BrowserWindow | null;
    getPreferences: () => { notifyOnTaskDone: boolean };
}): void {
    getBackendPort = deps.getBackendPort;
    getMainWin = deps.getMainWin;
    prefsGetter = deps.getPreferences;
    stopped = false;
    if (pollTimer) clearInterval(pollTimer);
    // 首次拉取建立基线，避免把已有终态任务误报为"新完成"
    void tick().then(() => {
        if (stopped) return;
        pollTimer = setInterval(() => void tick(), POLL_MS);
    });
}

export function stopNotifications(): void {
    stopped = true;
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}
