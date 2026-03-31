import type { TaskOut } from "@/services/api";
import type { TaskStreamEvent } from "@/hooks/useTaskStream";
import { TaskAlerts } from "@/components/features/task-detail/TaskAlerts";
import { TaskCoverageRange } from "@/components/features/task-detail/TaskCoverageRange";
import { TaskLiveHealth } from "@/components/features/task-detail/TaskLiveHealth";
import { TaskLiveKpiBar } from "@/components/features/task-detail/TaskLiveKpiBar";
import { TaskLiveTimeline } from "@/components/features/task-detail/TaskLiveTimeline";
import { TaskRuntimeMetrics } from "@/components/features/task-detail/TaskRuntimeMetrics";
import { TaskSegmentProgress } from "@/components/features/task-detail/TaskSegmentProgress";
import { TaskStatusBadge } from "@/components/features/task-detail/TaskStatusBadge";

export function TaskDetailOverview({
    task,
    active,
    isRiskPaused,
    latestActionEvent,
    streamConnected,
    streamEvents,
}: {
    task: TaskOut;
    active: boolean;
    isRiskPaused: boolean;
    latestActionEvent: TaskStreamEvent | null;
    streamConnected: boolean;
    streamEvents: TaskStreamEvent[];
}) {
    return (
        <>
            <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-2xl border bg-card p-5 shadow-sm">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">当前状态</p>
                    <TaskStatusBadge status={task.status} riskState={task.risk_state} />
                </div>

                <div className="rounded-2xl border bg-card p-5 shadow-sm">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">采集进度</p>
                    <div className="mb-2 flex items-baseline gap-2">
                        <span className="font-mono text-3xl font-semibold">{task.result_count}</span>
                        <span className="text-sm text-muted-foreground">条</span>
                    </div>
                    <p className="text-sm text-muted-foreground">{active && task.current_page > 0 ? `当前已抓到第 ${task.current_page} 页` : "会持续采集直到数据耗尽或被终止。"}</p>
                </div>

                <TaskRuntimeMetrics qualityState={task.quality_state} runtimeMetrics={task.runtime_metrics} />
            </div>

            <TaskAlerts error={task.error} isRiskPaused={isRiskPaused} riskState={task.risk_state} debugScreenshot={task.debug_screenshot} />

            {active ? (
                <div className="space-y-3">
                    <TaskLiveKpiBar task={task} connected={streamConnected} />
                    <TaskSegmentProgress task={task} />
                    <TaskLiveHealth task={task} />
                    <TaskCoverageRange task={task} />
                    <TaskLiveTimeline events={streamEvents.length > 0 ? streamEvents : latestActionEvent ? [latestActionEvent] : []} />
                </div>
            ) : task.result_count > 0 ? (
                <div className="space-y-3">
                    <TaskSegmentProgress task={task} />
                    <TaskCoverageRange task={task} />
                </div>
            ) : null}
        </>
    );
}
