import type { TaskOut, TaskStatus } from "@/services/api";

export function isTaskActive(status: TaskStatus) {
    return status === "running" || status === "pending" || status === "paused";
}

export function canResumeTask(status: TaskStatus) {
    return status === "done" || status === "failed" || status === "stopped";
}

export function formatDateTime(value?: string | null) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "--";
    return date.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

export function formatDate(value?: string | null) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "--";
    return date.toLocaleDateString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
    });
}

export function getCoverageSummary(range?: Record<string, unknown>) {
    if (!range) return "未生成覆盖时间";
    const start = typeof range.combined_start_at === "string" ? range.combined_start_at : "";
    const end = typeof range.combined_end_at === "string" ? range.combined_end_at : "";
    if (!start || !end) return "未生成覆盖时间";
    return `${formatDate(start)} - ${formatDate(end)}`;
}

export function getTaskPhase(task: Pick<TaskOut, "crawl_phase" | "latest_action">) {
    if (typeof task.crawl_phase === "string" && task.crawl_phase.trim()) {
        return task.crawl_phase.trim();
    }
    const latest = task.latest_action;
    if (latest && typeof latest.phase === "string" && latest.phase.trim()) {
        return latest.phase.trim();
    }
    return "等待任务更新";
}

export function getTaskLastUpdated(task: Pick<TaskOut, "last_event_at" | "finished_at" | "created_at">) {
    return task.last_event_at ?? task.finished_at ?? task.created_at;
}
