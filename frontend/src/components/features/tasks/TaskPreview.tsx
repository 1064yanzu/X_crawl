import Link from "next/link";
import { ExternalLink, Loader2, RefreshCcw, RotateCcw, Trash2, X } from "lucide-react";
import type { TaskOut } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TaskCommentBackfillButton } from "@/components/features/tasks/TaskCommentBackfillButton";
import { TaskStatusBadge } from "@/components/features/task-detail/TaskStatusBadge";
import { canCreateCommentBackfillFromTask, canRecrawlTask, canResumeTask, formatDateTime, getCommentBackfillSummary, getCoverageSummary, getRiskStateHint, getRiskStateLabel, getTaskKindLabel, getTaskLastUpdated, getTaskPhase, isTaskActive } from "@/lib/task-ui";
import { getPlatformMeta } from "@/lib/platformRegistry";
import { cn } from "@/lib/utils";

function PreviewStat({ label, value, hint }: { label: string; value: string; hint: string }) {
    return (
        <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-4 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
            <p className="mt-2 text-lg font-semibold text-foreground">{value}</p>
            <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
        </div>
    );
}

function TaskPreviewBody({
    task,
    resumingId,
    backfillingId,
    recrawlingId,
    onResume,
    onCommentBackfill,
    onRecrawl,
    onDelete,
}: {
    task: TaskOut;
    resumingId: string | null;
    backfillingId: string | null;
    recrawlingId: string | null;
    onResume: (taskId: string) => void;
    onCommentBackfill: (taskId: string) => void;
    onRecrawl: (taskId: string) => void;
    onDelete: (taskId: string) => void;
}) {
    const platformMeta = getPlatformMeta(task.platform);
    const phase = getTaskPhase(task);
    const coverage = getCoverageSummary(task.time_coverage as Record<string, unknown> | undefined);
    const active = isTaskActive(task.status);
    const backfillSummary = getCommentBackfillSummary(task);
    const canBackfill = canCreateCommentBackfillFromTask(task);
    const canRecrawl = canRecrawlTask(task);

    return (
        <>
            <div className="space-y-5 p-5">
                <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                        <span className={cn("inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium", platformMeta.badgeClass)}>{platformMeta.label}</span>
                        <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground">{getTaskKindLabel(task)}</span>
                        <TaskStatusBadge status={task.status} riskState={task.risk_state} size="sm" />
                        {active ? <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">进行中</span> : null}
                    </div>

                    <div>
                        <h3 className="text-2xl font-semibold tracking-tight text-foreground">{task.keyword}</h3>
                        <p className="mt-2 text-sm leading-6 text-muted-foreground">{phase}</p>
                    </div>

                    <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-3 text-sm text-muted-foreground shadow-sm">
                        <p>任务 ID：<span className="font-mono text-foreground">{task.task_id}</span></p>
                        <p className="mt-1">最近更新：{formatDateTime(getTaskLastUpdated(task))}</p>
                    </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                    <PreviewStat
                        label="结果数"
                        value={
                            task.source_task_id && (task.exclude_count ?? 0) > 0
                                ? `原始 ${(task.exclude_count ?? 0).toLocaleString()} · 新增 ${task.result_count.toLocaleString()}`
                                : `${task.result_count.toLocaleString()}`
                        }
                        hint="持续抓取直到数据耗尽或被终止"
                    />
                    <PreviewStat
                        label={task.task_kind === "comment_backfill" ? "补采进度" : "当前页"}
                        value={task.task_kind === "comment_backfill" ? (backfillSummary || "--") : task.current_page > 0 ? `${task.current_page}` : "--"}
                        hint={task.finished_at ? `结束于 ${formatDateTime(task.finished_at)}` : "仍在持续更新"}
                    />
                    <PreviewStat label="覆盖时间" value={coverage} hint={formatDateTime(task.created_at)} />
                    <PreviewStat label="风控状态" value={getRiskStateLabel(task.risk_state)} hint={task.status === "done" ? "任务已完成" : active ? getRiskStateHint(task.risk_state) : "可在详情页复盘"} />
                </div>

                <div className="rounded-[1.25rem] border border-border/60 bg-card/90 p-4 shadow-sm">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">快速判断</p>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span className="rounded-full bg-muted px-2.5 py-1">平台 {platformMeta.label}</span>
                        <span className="rounded-full bg-muted px-2.5 py-1">状态 {task.status}</span>
                        <span className="rounded-full bg-muted px-2.5 py-1">类型 {getTaskKindLabel(task)}</span>
                        <span className="rounded-full bg-muted px-2.5 py-1">
                            {task.source_task_id && (task.exclude_count ?? 0) > 0
                                ? `原始 ${(task.exclude_count ?? 0).toLocaleString()} · 新增 ${task.result_count.toLocaleString()}`
                                : `结果 ${task.result_count.toLocaleString()}`}
                        </span>
                        {task.fetch_replies ? <span className="rounded-full bg-muted px-2.5 py-1">已抓评论</span> : null}
                        {task.resumed ? <span className="rounded-full bg-muted px-2.5 py-1">曾恢复过</span> : null}
                    </div>
                </div>
            </div>

            <div className="border-t border-border/60 px-5 py-4 sm:px-6">
                <div className="flex flex-col gap-2 sm:flex-row">
                    <Link href={`/tasks/${task.task_id}`} className="flex-1">
                        <Button className="w-full rounded-xl">
                            <ExternalLink className="mr-1.5 h-4 w-4" />
                            打开完整详情
                        </Button>
                    </Link>

                    {canResumeTask(task.status) ? (
                        <Button
                            variant="outline"
                            className="rounded-xl"
                            disabled={resumingId === task.task_id}
                            onClick={() => onResume(task.task_id)}
                        >
                            {resumingId === task.task_id ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-1.5 h-4 w-4" />}
                            继续
                        </Button>
                    ) : null}

                    {canBackfill ? (
                        <TaskCommentBackfillButton
                            variant="outline"
                            className="rounded-xl"
                            loading={backfillingId === task.task_id}
                            onClick={() => onCommentBackfill(task.task_id)}
                        />
                    ) : null}

                    {canRecrawl ? (
                        <Button
                            variant="outline"
                            className="rounded-xl"
                            disabled={recrawlingId === task.task_id}
                            onClick={() => onRecrawl(task.task_id)}
                        >
                            {recrawlingId === task.task_id ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-1.5 h-4 w-4" />}
                            增量复爬
                        </Button>
                    ) : null}

                    <Button variant="outline" className="rounded-xl text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-500/10" onClick={() => onDelete(task.task_id)}>
                        <Trash2 className="mr-1.5 h-4 w-4" />
                        删除
                    </Button>
                </div>
            </div>
        </>
    );
}

export function TaskPreviewPanel({
    task,
    resumingId,
    backfillingId,
    recrawlingId,
    onResume,
    onCommentBackfill,
    onRecrawl,
    onDelete,
}: {
    task: TaskOut | null;
    resumingId: string | null;
    backfillingId: string | null;
    recrawlingId: string | null;
    onResume: (taskId: string) => void;
    onCommentBackfill: (taskId: string) => void;
    onRecrawl: (taskId: string) => void;
    onDelete: (taskId: string) => void;
}) {
    if (!task) {
        return (
            <Card className="rounded-[1.75rem] border-border/60 bg-card/90 p-5 shadow-sm backdrop-blur-sm">
                <div className="space-y-4">
                    <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Live Preview</p>
                        <h2 className="mt-1 text-xl font-semibold text-foreground">右侧任务预览</h2>
                        <p className="mt-1 text-sm leading-6 text-muted-foreground">选择任务后会在这里显示预览。</p>
                    </div>
                    <div className="rounded-[1.25rem] border border-dashed border-border/70 bg-background/60 p-4 text-sm leading-6 text-muted-foreground">
                        当前没有可预览的任务。你可以先调整平台筛选、搜索条件，或返回控制台创建新的采集任务。
                    </div>
                </div>
            </Card>
        );
    }

    return (
        <Card className="overflow-hidden rounded-[1.75rem] border-border/60 bg-card/90 shadow-sm backdrop-blur-sm">
            <div className="border-b border-border/60 px-5 py-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Live Preview</p>
                <h2 className="mt-1 text-xl font-semibold text-foreground">右侧任务预览</h2>
                <p className="mt-1 text-sm text-muted-foreground">当前任务概览。</p>
            </div>
            <TaskPreviewBody task={task} resumingId={resumingId} backfillingId={backfillingId} recrawlingId={recrawlingId} onResume={onResume} onCommentBackfill={onCommentBackfill} onRecrawl={onRecrawl} onDelete={onDelete} />
        </Card>
    );
}

export function TaskPreviewDrawer({
    task,
    resumingId,
    backfillingId,
    recrawlingId,
    onClose,
    onResume,
    onCommentBackfill,
    onRecrawl,
    onDelete,
}: {
    task: TaskOut | null;
    resumingId: string | null;
    backfillingId: string | null;
    recrawlingId: string | null;
    onClose: () => void;
    onResume: (taskId: string) => void;
    onCommentBackfill: (taskId: string) => void;
    onRecrawl: (taskId: string) => void;
    onDelete: (taskId: string) => void;
}) {
    if (!task) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/45 p-0 backdrop-blur-sm xl:hidden">
            <div className="max-h-[92vh] w-full overflow-hidden rounded-t-[2rem] border border-border/60 bg-card shadow-2xl">
                <div className="flex items-center justify-between border-b border-border/60 px-5 py-4">
                    <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Live Preview</p>
                        <h2 className="mt-1 text-lg font-semibold text-foreground">任务快速预览</h2>
                    </div>
                    <Button variant="ghost" size="icon" className="rounded-xl" onClick={onClose} aria-label="关闭任务预览">
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                <div className="max-h-[calc(92vh-84px)] overflow-y-auto">
                    <TaskPreviewBody task={task} resumingId={resumingId} backfillingId={backfillingId} recrawlingId={recrawlingId} onResume={onResume} onCommentBackfill={onCommentBackfill} onRecrawl={onRecrawl} onDelete={onDelete} />
                </div>
            </div>
        </div>
    );
}
