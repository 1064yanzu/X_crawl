import Link from "next/link";
import { Eye, ExternalLink, Loader2, RefreshCcw, Trash2 } from "lucide-react";
import type { TaskOut } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TaskStatusBadge } from "@/components/features/task-detail/TaskStatusBadge";
import { TaskCommentBackfillButton } from "@/components/features/tasks/TaskCommentBackfillButton";
import { TaskMetaBlock } from "@/components/features/tasks/TaskMetaBlock";
import { getPlatformMeta } from "@/lib/platformRegistry";
import { canCreateCommentBackfillFromTask, canResumeTask, formatDateTime, getCommentBackfillSummary, getCoverageSummary, getTaskKindLabel, getTaskLastUpdated, getTaskPhase, getTaskQueueLabel } from "@/lib/task-ui";
import { cn } from "@/lib/utils";
import type { DensityMode } from "@/hooks/useTaskListState";

export function TaskListCard({
    task,
    density,
    selected,
    focused,
    busyAction,
    resumingId,
    backfillingId,
    onHover,
    onSelect,
    onPreview,
    onResume,
    onCommentBackfill,
    onDelete,
}: {
    task: TaskOut;
    density: DensityMode;
    selected: boolean;
    focused: boolean;
    busyAction: "resume" | "backfill" | "delete" | null;
    resumingId: string | null;
    backfillingId: string | null;
    onHover: (taskId: string) => void;
    onSelect: (taskId: string, checked: boolean) => void;
    onPreview: (taskId: string) => void;
    onResume: (taskId: string) => void;
    onCommentBackfill: (taskId: string) => void;
    onDelete: (taskId: string) => void;
}) {
    const platformMeta = getPlatformMeta(task.platform);
    const phase = getTaskPhase(task);
    const lastUpdated = formatDateTime(getTaskLastUpdated(task));
    const coverage = getCoverageSummary(task.time_coverage as Record<string, unknown> | undefined);
    const isBackfill = task.task_kind === "comment_backfill";
    const progressSummary = getCommentBackfillSummary(task);
    const queueLabel = getTaskQueueLabel(task);
    const canBackfill = canCreateCommentBackfillFromTask(task);

    return (
        <Card
            id={`task-card-${task.task_id}`}
            className={cn(
                "overflow-hidden border-border/60 bg-card/90 shadow-sm transition-all",
                density === "compact" ? "rounded-[1.25rem]" : "rounded-[1.5rem]",
                selected && "border-primary/50 ring-2 ring-primary/10",
                focused && "border-sky-400/60 ring-2 ring-sky-500/15",
            )}
            onMouseEnter={() => onHover(task.task_id)}
        >
            <div className="flex flex-col lg:flex-row">
                <Link href={`/tasks/${task.task_id}`} className={cn("flex-1", density === "compact" ? "p-4 sm:p-5" : "p-5 sm:p-6")}>
                    <div className={cn("flex flex-col", density === "compact" ? "gap-3" : "gap-4")}>
                        <div className="flex flex-wrap items-center gap-2">
                            {focused ? <span className="rounded-full bg-sky-500/10 px-2.5 py-1 text-[11px] font-medium text-sky-700 dark:text-sky-300">当前焦点</span> : null}
                            <span className={cn("inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium", platformMeta.badgeClass)}>
                                {platformMeta.label}
                            </span>
                            <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                                {getTaskKindLabel(task)}
                            </span>
                            {canBackfill ? <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-700 dark:text-emerald-300">可补采评论</span> : null}
                            {queueLabel ? <span className="rounded-full bg-primary/8 px-2.5 py-1 text-[11px] font-medium text-primary">队列 {queueLabel}</span> : null}
                            <TaskStatusBadge status={task.status} riskState={task.risk_state} size="sm" />
                            <code className="rounded-full bg-muted px-2.5 py-1 text-[11px] text-muted-foreground">{task.task_id.slice(0, 8)}</code>
                        </div>

                        <div>
                            <h3 className={cn("line-clamp-2 font-semibold tracking-tight text-foreground", density === "compact" ? "text-lg" : "text-xl")}>{task.keyword}</h3>
                            <p className={cn("line-clamp-2 text-sm text-muted-foreground", density === "compact" ? "mt-1.5 leading-5" : "mt-2 leading-6")}>{phase}</p>
                        </div>

                        <div className={cn("grid md:grid-cols-2 xl:grid-cols-4", density === "compact" ? "gap-2" : "gap-3")}>
                            <TaskMetaBlock label="结果数" value={`${task.result_count}`} compact={density === "compact"} />
                            <TaskMetaBlock
                                label={isBackfill ? "补采进度" : "当前页"}
                                value={isBackfill ? (progressSummary || "--") : task.current_page > 0 ? `${task.current_page}` : "--"}
                                compact={density === "compact"}
                            />
                            <TaskMetaBlock label="覆盖时间" value={coverage} compact={density === "compact"} />
                            <TaskMetaBlock label="最近更新" value={lastUpdated} compact={density === "compact"} />
                        </div>
                    </div>
                </Link>

                <div className={cn("border-t border-border/50 bg-muted/15 lg:border-l lg:border-t-0", density === "compact" ? "p-3 lg:w-[220px]" : "p-4 lg:w-[236px]")}>
                    <div className={cn("flex h-full flex-col", density === "compact" ? "gap-2.5" : "gap-3")}>
                        <label className="inline-flex items-center gap-2 self-start rounded-full border border-border/60 bg-card px-3 py-1.5 text-xs font-medium text-foreground shadow-sm">
                            <input
                                type="checkbox"
                                checked={selected}
                                onChange={(event) => onSelect(task.task_id, event.target.checked)}
                                className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
                            />
                            选中此任务
                        </label>

                        <div className="w-full rounded-2xl border border-border/60 bg-card px-3 py-3 text-xs text-muted-foreground shadow-sm">
                            <p className="font-semibold uppercase tracking-[0.16em]">任务信息</p>
                            <p className="mt-2">创建于 {formatDateTime(task.created_at)}</p>
                            {task.finished_at ? <p className="mt-1">结束于 {formatDateTime(task.finished_at)}</p> : null}
                        </div>

                        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                            <Button variant="outline" size="sm" className="justify-start rounded-xl" onClick={() => onPreview(task.task_id)}>
                                <Eye className="mr-1.5 h-3.5 w-3.5" />
                                快速预览
                            </Button>

                            {canBackfill ? (
                                <TaskCommentBackfillButton
                                    variant="outline"
                                    size="sm"
                                    className="justify-start rounded-xl"
                                    disabled={busyAction !== null}
                                    loading={backfillingId === task.task_id}
                                    onClick={() => onCommentBackfill(task.task_id)}
                                />
                            ) : null}

                            {canResumeTask(task.status) ? (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="justify-start rounded-xl"
                                    disabled={resumingId === task.task_id || busyAction !== null}
                                    onClick={() => onResume(task.task_id)}
                                >
                                    {resumingId === task.task_id ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="mr-1.5 h-3.5 w-3.5" />}
                                    继续
                                </Button>
                            ) : null}
                        </div>

                        <div className="mt-auto flex gap-2 lg:justify-end">
                            <Link href={`/tasks/${task.task_id}`} className="flex-1 lg:flex-none">
                                <Button variant="ghost" size="sm" className="w-full rounded-xl text-muted-foreground">
                                    <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                                    详情
                                </Button>
                            </Link>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="rounded-xl text-muted-foreground hover:text-red-600"
                                onClick={() => onDelete(task.task_id)}
                                disabled={busyAction !== null}
                            >
                                <Trash2 className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    );
}
