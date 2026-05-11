import * as React from "react";
import Link from "next/link";
import { Eye, ExternalLink, Loader2, MessageCircleMore, RefreshCcw, RotateCcw, Trash2, Zap } from "lucide-react";
import type { TaskOut } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TaskStatusBadge } from "@/components/features/task-detail/TaskStatusBadge";
import { TaskMetaBlock } from "@/components/features/tasks/TaskMetaBlock";
import { getPlatformMeta } from "@/lib/platformRegistry";
import { canCreateCommentBackfillFromTask, canRecrawlTask, canResumeTask, formatDateTime, getCommentBackfillPercent, getCommentBackfillSummary, getCoverageSummary, getTaskKindLabel, getTaskLastUpdated, getTaskPhase, getTaskQueueLabel } from "@/lib/task-ui";
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
    recrawlingId,
    onHover,
    onSelect,
    onPreview,
    onResume,
    onCommentBackfill,
    onRecrawl,
    onDelete,
}: {
    task: TaskOut;
    density: DensityMode;
    selected: boolean;
    focused: boolean;
    busyAction: "resume" | "resumeAll" | "pauseAll" | "batchPause" | "backfill" | "recrawl" | "delete" | "export" | "merge" | null;
    resumingId: string | null;
    backfillingId: string | null;
    recrawlingId: string | null;
    onHover: (taskId: string) => void;
    onSelect: (taskId: string, checked: boolean) => void;
    onPreview: (taskId: string) => void;
    onResume: (taskId: string, options?: { concurrency?: number }) => void;
    onCommentBackfill: (taskId: string) => void;
    onRecrawl: (taskId: string) => void;
    onDelete: (taskId: string) => void;
}) {
    if (density === "mini") {
        return (
            <TaskListCardMini
                task={task}
                selected={selected}
                focused={focused}
                busyAction={busyAction}
                resumingId={resumingId}
                backfillingId={backfillingId}
                recrawlingId={recrawlingId}
                onHover={onHover}
                onSelect={onSelect}
                onPreview={onPreview}
                onResume={onResume}
                onCommentBackfill={onCommentBackfill}
                onRecrawl={onRecrawl}
                onDelete={onDelete}
            />
        );
    }

    if (density === "compact") {
        return (
            <TaskListCardCompact
                task={task}
                selected={selected}
                focused={focused}
                busyAction={busyAction}
                resumingId={resumingId}
                backfillingId={backfillingId}
                recrawlingId={recrawlingId}
                onHover={onHover}
                onSelect={onSelect}
                onPreview={onPreview}
                onResume={onResume}
                onCommentBackfill={onCommentBackfill}
                onRecrawl={onRecrawl}
                onDelete={onDelete}
            />
        );
    }

    return (
        <TaskListCardComfortable
            task={task}
            selected={selected}
            focused={focused}
            busyAction={busyAction}
            resumingId={resumingId}
            backfillingId={backfillingId}
            recrawlingId={recrawlingId}
            onHover={onHover}
            onSelect={onSelect}
            onPreview={onPreview}
            onResume={onResume}
            onCommentBackfill={onCommentBackfill}
            onRecrawl={onRecrawl}
            onDelete={onDelete}
        />
    );
}

/* ───────────────────────── 共享 Props 类型 ───────────────────────── */

type CardInnerProps = Omit<Parameters<typeof TaskListCard>[0], "density">;

/* ────────────────────── Comfortable（原始大卡片） ────────────────── */

function TaskListCardComfortable({
    task,
    selected,
    focused,
    busyAction,
    resumingId,
    backfillingId,
    recrawlingId,
    onHover,
    onSelect,
    onPreview,
    onResume,
    onCommentBackfill,
    onRecrawl,
    onDelete,
}: CardInnerProps) {
    const platformMeta = getPlatformMeta(task.platform);
    const phase = getTaskPhase(task);
    const lastUpdated = formatDateTime(getTaskLastUpdated(task));
    const coverage = getCoverageSummary(task.time_coverage as Record<string, unknown> | undefined);
    const isBackfill = task.task_kind === "comment_backfill";
    const progressSummary = getCommentBackfillSummary(task);
    const backfillPercent = getCommentBackfillPercent(task);
    const queueLabel = getTaskQueueLabel(task);
    const canBackfill = canCreateCommentBackfillFromTask(task);
    const showRecrawl = canRecrawlTask(task);
    const isGroup = task.task_kind === "comment_backfill_group";
    const canResume = canResumeTask(task.status);
    const [groupConcurrency, setGroupConcurrency] = React.useState(task.concurrency ?? 1);

    return (
        <Card
            id={`task-card-${task.task_id}`}
            className={cn(
 "overflow-hidden rounded-lg border-border bg-card shadow-sm transition-all",
                selected && "border-primary/50 ring-2 ring-primary/10",
                focused && "border-sky-400/60 ring-2 ring-sky-500/15",
            )}
            onMouseEnter={() => onHover(task.task_id)}
        >
            <div className="flex flex-col lg:flex-row">
                <Link href={`/tasks/${task.task_id}`} className="flex-1 p-5 sm:p-6">
                    <div className="flex flex-col gap-4">
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
                            <h3 className="line-clamp-2 text-xl font-semibold tracking-tight text-foreground">{task.keyword}</h3>
                            <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{phase}</p>
                        </div>

                        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                            <TaskMetaBlock
                                label="结果数"
                                value={
                                    task.source_task_id && (task.exclude_count ?? 0) > 0
                                        ? `原始 ${(task.exclude_count ?? 0).toLocaleString()} · 新增 ${task.result_count.toLocaleString()}`
                                        : `${task.result_count.toLocaleString()}`
                                }
                            />
                            {isBackfill ? (
                                <div className="flex flex-col gap-1.5">
                                    <span className="text-xs font-medium text-muted-foreground">补采进度</span>
                                    <div className="flex items-center gap-2">
                                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                                            <div
                                                className="h-full rounded-full bg-primary transition-all duration-500"
                                                style={{ width: `${backfillPercent}%` }}
                                            />
                                        </div>
                                        <span className="shrink-0 text-xs font-semibold tabular-nums text-foreground">{backfillPercent}%</span>
                                    </div>
                                    <span className="text-[11px] text-muted-foreground">{progressSummary || "--"}</span>
                                </div>
                            ) : (
                                <TaskMetaBlock
                                    label="当前页"
                                    value={task.current_page > 0 ? `${task.current_page}` : "--"}
                                />
                            )}
                            <TaskMetaBlock label="覆盖时间" value={coverage} />
                            <TaskMetaBlock label="最近更新" value={lastUpdated} />
                        </div>
                    </div>
                </Link>

                <div className="border-t border-border bg-muted/15 p-4 lg:w-[236px] lg:border-l lg:border-t-0">
                    <div className="flex h-full flex-col gap-3">
                        <label className="inline-flex items-center gap-2 self-start rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground shadow-sm">
                            <input
                                type="checkbox"
                                checked={selected}
                                onChange={(event) => onSelect(task.task_id, event.target.checked)}
                                className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
                            />
                            选中此任务
                        </label>

                        <div className="w-full rounded-md border border-border bg-card px-3 py-3 text-xs text-muted-foreground shadow-sm">
                            <p className="font-semibold uppercase tracking-[0.16em]">任务信息</p>
                            <p className="mt-2">创建于 {formatDateTime(task.created_at)}</p>
                            {task.finished_at ? <p className="mt-1">结束于 {formatDateTime(task.finished_at)}</p> : null}
                        </div>

                        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                            <Button variant="outline" size="sm" className="justify-start rounded-md" onClick={() => onPreview(task.task_id)}>
                                <Eye className="mr-1.5 h-3.5 w-3.5" />
                                快速预览
                            </Button>

                            {canBackfill ? (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="justify-start rounded-md"
                                    disabled={busyAction !== null}
                                    onClick={() => onCommentBackfill(task.task_id)}
                                >
                                    {backfillingId === task.task_id ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <MessageCircleMore className="mr-1.5 h-3.5 w-3.5" />}
                                    补采评论
                                </Button>
                            ) : null}

                            {canResume && isGroup ? (
                                <div className="col-span-full space-y-2">
                                    <div className="flex items-center gap-1.5">
                                        <Zap className="h-3 w-3 text-muted-foreground" />
                                        <span className="text-[11px] font-medium text-muted-foreground">并发数</span>
                                        <div className="flex items-center gap-1">
                                            {[1, 2, 3, 4, 5].map((n) => (
                                                <button
                                                    key={n}
                                                    type="button"
                                                    className={cn(
 "flex h-6 w-7 items-center justify-center rounded-md border text-[11px] font-medium transition-colors",
                                                        groupConcurrency === n
                                                            ? "border-violet-500 bg-violet-500/10 text-violet-700 dark:text-violet-300"
                                                            : "border-border bg-background text-muted-foreground hover:border-violet-500/50",
                                                    )}
                                                    onClick={() => setGroupConcurrency(n)}
                                                    disabled={resumingId === task.task_id || busyAction !== null}
                                                >
                                                    {n}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="w-full justify-start rounded-md"
                                        disabled={resumingId === task.task_id || busyAction !== null}
                                        onClick={() => onResume(task.task_id, { concurrency: groupConcurrency })}
                                    >
                                        {resumingId === task.task_id ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="mr-1.5 h-3.5 w-3.5" />}
                                        {groupConcurrency > 1 ? `继续（${groupConcurrency} 路并发）` : "继续"}
                                    </Button>
                                </div>
                            ) : canResume ? (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="justify-start rounded-md"
                                    disabled={resumingId === task.task_id || busyAction !== null}
                                    onClick={() => onResume(task.task_id)}
                                >
                                    {resumingId === task.task_id ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="mr-1.5 h-3.5 w-3.5" />}
                                    继续
                                </Button>
                            ) : null}

                            {showRecrawl ? (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="justify-start rounded-md"
                                    disabled={recrawlingId === task.task_id || busyAction !== null}
                                    onClick={() => onRecrawl(task.task_id)}
                                >
                                    {recrawlingId === task.task_id ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="mr-1.5 h-3.5 w-3.5" />}
                                    增量复爬
                                </Button>
                            ) : null}
                        </div>

                        <div className="mt-auto flex gap-2 lg:justify-end">
                            <Link href={`/tasks/${task.task_id}`} className="flex-1 lg:flex-none">
                                <Button variant="ghost" size="sm" className="w-full rounded-md text-muted-foreground">
                                    <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                                    详情
                                </Button>
                            </Link>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="rounded-md text-muted-foreground hover:text-red-600"
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

/* ────────────────────── Compact（紧凑行式布局） ─────────────────── */

function TaskListCardCompact({
    task,
    selected,
    focused,
    busyAction,
    resumingId,
    backfillingId,
    recrawlingId,
    onHover,
    onSelect,
    onPreview,
    onResume,
    onCommentBackfill,
    onRecrawl,
    onDelete,
}: CardInnerProps) {
    const [hovered, setHovered] = React.useState(false);
    const platformMeta = getPlatformMeta(task.platform);
    const phase = getTaskPhase(task);
    const lastUpdated = formatDateTime(getTaskLastUpdated(task));
    const isBackfill = task.task_kind === "comment_backfill";
    const progressSummary = getCommentBackfillSummary(task);
    const backfillPercent = getCommentBackfillPercent(task);
    const queueLabel = getTaskQueueLabel(task);
    const canBackfill = canCreateCommentBackfillFromTask(task);
    const showRecrawl = canRecrawlTask(task);

    return (
        <Card
            id={`task-card-${task.task_id}`}
            className={cn(
 "group relative overflow-hidden rounded-md border-border bg-card shadow-sm transition-all hover:shadow-md",
                selected && "border-primary/50 ring-2 ring-primary/10",
                focused && "border-sky-400/60 ring-2 ring-sky-500/15",
            )}
            onMouseEnter={() => { onHover(task.task_id); setHovered(true); }}
            onMouseLeave={() => setHovered(false)}
        >
            <div className="flex items-center gap-3 px-4 py-3">
                {/* 复选框 */}
                <input
                    type="checkbox"
                    checked={selected}
                    onChange={(event) => onSelect(task.task_id, event.target.checked)}
                    className="h-4 w-4 shrink-0 rounded border-input text-primary focus:ring-primary"
                />

                {/* 状态 badge */}
                <TaskStatusBadge status={task.status} riskState={task.risk_state} size="sm" />

                {/* 平台 badge */}
                <span className={cn("inline-flex shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium", platformMeta.badgeClass)}>
                    {platformMeta.label}
                </span>

                {/* 关键词 & 阶段 */}
                <Link href={`/tasks/${task.task_id}`} className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                        <h3 className="truncate text-sm font-semibold text-foreground">{task.keyword}</h3>
                        <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">{getTaskKindLabel(task)}</span>
                        {queueLabel ? <span className="hidden shrink-0 rounded-full bg-primary/8 px-2 py-0.5 text-[10px] font-medium text-primary lg:inline">队列 {queueLabel}</span> : null}
                    </div>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">{phase}</p>
                </Link>

                {/* 指标区域 */}
                <div className="hidden shrink-0 items-center gap-4 text-xs text-muted-foreground md:flex">
                    <div className="text-right">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">结果</p>
                        <p className="font-medium tabular-nums text-foreground">
                            {task.source_task_id && (task.exclude_count ?? 0) > 0
                                ? `${(task.exclude_count ?? 0).toLocaleString()}+${task.result_count.toLocaleString()}`
                                : task.result_count.toLocaleString()}
                        </p>
                    </div>
                    {isBackfill ? (
                        <div className="flex min-w-[100px] flex-col items-end gap-0.5">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">进度</p>
                            <div className="flex w-full items-center gap-1.5">
                                <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
                                    <div
                                        className="h-full rounded-full bg-primary transition-all duration-500"
                                        style={{ width: `${backfillPercent}%` }}
                                    />
                                </div>
                                <span className="text-[11px] font-medium tabular-nums text-foreground">{backfillPercent}%</span>
                            </div>
                        </div>
                    ) : (
                        <div className="text-right">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">页码</p>
                            <p className="font-medium tabular-nums text-foreground">
                                {task.current_page > 0 ? `${task.current_page}` : "--"}
                            </p>
                        </div>
                    )}
                    <div className="hidden text-right lg:block">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">更新</p>
                        <p className="font-medium text-foreground">{lastUpdated}</p>
                    </div>
                </div>

                {/* 操作按钮（hover 时显示） */}
                <div className={cn(
 "flex shrink-0 items-center gap-1 transition-opacity duration-150",
                    hovered ? "opacity-100" : "pointer-events-none opacity-0",
                )}>
                    <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg" onClick={() => onPreview(task.task_id)} title="快速预览">
                        <Eye className="h-3.5 w-3.5" />
                    </Button>
                    {canResumeTask(task.status) ? (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 rounded-lg"
                            disabled={resumingId === task.task_id || busyAction !== null}
                            onClick={() => onResume(task.task_id, task.task_kind === "comment_backfill_group" ? { concurrency: task.concurrency ?? 1 } : undefined)}
                            title={task.task_kind === "comment_backfill_group" ? `继续（${task.concurrency ?? 1} 路并发）` : "继续"}
                        >
                            {resumingId === task.task_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="h-3.5 w-3.5" />}
                        </Button>
                    ) : null}
                    {canBackfill ? (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 rounded-lg"
                            disabled={busyAction !== null}
                            onClick={() => onCommentBackfill(task.task_id)}
                            title="补采评论"
                        >
                            {backfillingId === task.task_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MessageCircleMore className="h-3.5 w-3.5" />}
                        </Button>
                    ) : null}
                    {showRecrawl ? (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 rounded-lg"
                            disabled={recrawlingId === task.task_id || busyAction !== null}
                            onClick={() => onRecrawl(task.task_id)}
                            title="增量复爬"
                        >
                            {recrawlingId === task.task_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                        </Button>
                    ) : null}
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 rounded-lg text-muted-foreground hover:text-red-600"
                        onClick={() => onDelete(task.task_id)}
                        disabled={busyAction !== null}
                        title="删除"
                    >
                        <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                </div>
            </div>
        </Card>
    );
}

/* ──────────────────────── Mini（极简表格行） ─────────────────────── */

function TaskListCardMini({
    task,
    selected,
    focused,
    busyAction,
    resumingId,
    backfillingId,
    recrawlingId,
    onHover,
    onSelect,
    onPreview,
    onResume,
    onCommentBackfill,
    onRecrawl,
    onDelete,
}: CardInnerProps) {
    const [hovered, setHovered] = React.useState(false);
    const platformMeta = getPlatformMeta(task.platform);
    const canBackfill = canCreateCommentBackfillFromTask(task);
    const showRecrawl = canRecrawlTask(task);
    const lastUpdated = formatDateTime(getTaskLastUpdated(task));

    return (
        <div
            id={`task-card-${task.task_id}`}
            className={cn(
 "group flex items-center gap-2.5 rounded-md border border-transparent px-3 py-2 text-sm transition-all hover:bg-muted/40",
                selected && "border-primary/40 bg-primary/5",
                focused && "border-sky-400/50 bg-sky-500/5",
            )}
            onMouseEnter={() => { onHover(task.task_id); setHovered(true); }}
            onMouseLeave={() => setHovered(false)}
        >
            <input
                type="checkbox"
                checked={selected}
                onChange={(event) => onSelect(task.task_id, event.target.checked)}
                className="h-3.5 w-3.5 shrink-0 rounded border-input text-primary focus:ring-primary"
            />

            <TaskStatusBadge status={task.status} riskState={task.risk_state} size="xs" />

            <span className={cn("inline-flex shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium", platformMeta.badgeClass)}>
                {platformMeta.label}
            </span>

            <Link href={`/tasks/${task.task_id}`} className="min-w-0 flex-1 truncate font-medium text-foreground hover:underline">
                {task.keyword}
            </Link>

            <span className="hidden shrink-0 tabular-nums text-xs text-muted-foreground sm:inline">
                {task.result_count.toLocaleString()} 条
            </span>

            <span className="hidden shrink-0 text-xs text-muted-foreground lg:inline">
                {lastUpdated}
            </span>

            <code className="hidden shrink-0 text-[10px] text-muted-foreground/60 xl:inline">{task.task_id.slice(0, 8)}</code>

            {/* hover 操作 */}
            <div className={cn(
 "flex shrink-0 items-center gap-0.5 transition-opacity duration-100",
                hovered ? "opacity-100" : "pointer-events-none opacity-0",
            )}>
                <Button variant="ghost" size="icon" className="h-6 w-6 rounded-md" onClick={() => onPreview(task.task_id)} title="预览">
                    <Eye className="h-3 w-3" />
                </Button>
                {canResumeTask(task.status) ? (
                    <Button variant="ghost" size="icon" className="h-6 w-6 rounded-md" disabled={resumingId === task.task_id || busyAction !== null} onClick={() => onResume(task.task_id, task.task_kind === "comment_backfill_group" ? { concurrency: task.concurrency ?? 1 } : undefined)} title="继续">
                        {resumingId === task.task_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCcw className="h-3 w-3" />}
                    </Button>
                ) : null}
                {canBackfill ? (
                    <Button variant="ghost" size="icon" className="h-6 w-6 rounded-md" disabled={busyAction !== null} onClick={() => onCommentBackfill(task.task_id)} title="补采评论">
                        {backfillingId === task.task_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <MessageCircleMore className="h-3 w-3" />}
                    </Button>
                ) : null}
                {showRecrawl ? (
                    <Button variant="ghost" size="icon" className="h-6 w-6 rounded-md" disabled={recrawlingId === task.task_id || busyAction !== null} onClick={() => onRecrawl(task.task_id)} title="复爬">
                        {recrawlingId === task.task_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCcw className="h-3 w-3" />}
                    </Button>
                ) : null}
                <Button variant="ghost" size="icon" className="h-6 w-6 rounded-md text-muted-foreground hover:text-red-600" onClick={() => onDelete(task.task_id)} disabled={busyAction !== null} title="删除">
                    <Trash2 className="h-3 w-3" />
                </Button>
            </div>
        </div>
    );
}
