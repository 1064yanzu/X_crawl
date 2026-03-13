import type { TaskOut, TaskStatus, RiskState } from "@/services/api";

const RISK_STATE_LABELS: Record<RiskState, string> = {
    none: "正常",
    challenge: "安全验证",
    rate_limited: "请求受限",
    login_required: "需要重新登录",
    search_blocked: "搜索受限",
};

const RISK_STATE_HINTS: Record<RiskState, string> = {
    none: "当前未检测到异常风控",
    challenge: "请在浏览器完成安全验证后继续任务",
    rate_limited: "当前账号或 IP 请求过快，建议稍后重试",
    login_required: "当前会话登录态已失效，需要重新登录",
    search_blocked: "当前账号搜索接口异常，疑似被 X 限制搜索能力",
};

export function isTaskActive(status: TaskStatus) {
    return status === "running" || status === "pending" || status === "paused";
}

export function canResumeTask(status: TaskStatus) {
    return status === "done" || status === "failed" || status === "stopped";
}

export function getRiskStateLabel(riskState?: string | null) {
    if (!riskState || !(riskState in RISK_STATE_LABELS)) return riskState || "正常";
    return RISK_STATE_LABELS[riskState as RiskState];
}

export function getRiskStateHint(riskState?: string | null) {
    if (!riskState || !(riskState in RISK_STATE_HINTS)) return "可在详情页继续观察任务状态";
    return RISK_STATE_HINTS[riskState as RiskState];
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

export function getTaskKindLabel(task: Pick<TaskOut, "task_kind">) {
    return task.task_kind === "comment_backfill" ? "评论补采" : "帖子采集";
}

export function getTaskModeLabel(task: Pick<TaskOut, "task_kind" | "product">) {
    if (task.task_kind === "comment_backfill") return "评论补采";
    return task.product || "采集任务";
}

export function getCommentBackfillSummary(task: Pick<TaskOut, "task_kind" | "comment_backfill_progress">) {
    if (task.task_kind !== "comment_backfill") return "";
    const progress = task.comment_backfill_progress;
    if (!progress) return "等待导入结果";
    return `${progress.processed_posts}/${progress.eligible_posts} 已处理`;
}

export function getTaskQueueLabel(task: Pick<TaskOut, "queue_total" | "queue_order" | "queue_name">) {
    if (!task.queue_total || task.queue_total <= 1 || !task.queue_order) return "";
    const prefix = task.queue_name ? `${task.queue_name} · ` : "";
    return `${prefix}${task.queue_order}/${task.queue_total}`;
}
