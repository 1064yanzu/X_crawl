import { ArrowLeft, Copy, Loader2, Pause, Play, RotateCcw, StopCircle, Terminal, Zap } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import type { TaskOut } from "@/services/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TaskCommentBackfillButton } from "@/components/features/tasks/TaskCommentBackfillButton";
import { TaskStatusBadge } from "@/components/features/task-detail/TaskStatusBadge";
import { getPlatformMeta } from "@/lib/platformRegistry";
import { cn } from "@/lib/utils";
import { formatDateTime, getCommentBackfillPercent, getCommentBackfillSummary, getTaskKindLabel, getTaskModeLabel, getTaskPhase, getTaskQueueLabel } from "@/lib/task-ui";

function SummaryCard({ label, value, hint }: { label: string; value: string; hint: string }) {
    return (
        <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-4 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
            <p className="mt-2 text-lg font-semibold text-foreground">{value}</p>
            <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
        </div>
    );
}

function ConcurrencySelector({
    value,
    saving,
    active,
    onChange,
}: {
    value: number;
    saving: boolean;
    active: boolean;
    onChange: (n: number) => void;
}) {
    return (
        <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-4 shadow-sm">
            <div className="flex items-center gap-1.5">
                <Zap className="h-3.5 w-3.5 text-violet-500" />
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">并发数</p>
                {saving ? <Loader2 className="ml-1 h-3 w-3 animate-spin text-muted-foreground" /> : null}
            </div>
            <div className="mt-2 flex items-center gap-1.5">
                {[1, 2, 3, 4, 5].map((n) => (
                    <button
                        key={n}
                        type="button"
                        className={cn(
                            "flex h-8 w-9 items-center justify-center rounded-lg border text-sm font-semibold transition-all",
                            value === n
                                ? "border-violet-500 bg-violet-500/10 text-violet-700 shadow-sm dark:text-violet-300"
                                : "border-border bg-background text-muted-foreground hover:border-violet-500/50 hover:text-foreground",
                        )}
                        disabled={saving}
                        onClick={() => onChange(n)}
                    >
                        {n}
                    </button>
                ))}
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">
                {active ? "修改将在下次恢复时生效" : value > 1 ? `${value} 个 Pipeline 并行处理` : "单 Pipeline 模式"}
            </p>
        </div>
    );
}

function TaskExportPanel({
    resultCount,
    active,
    exporting,
    onExport,
}: {
    resultCount: number;
    active: boolean;
    exporting: "csv" | "excel" | null;
    onExport: (format: "csv" | "excel") => void;
}) {
    return (
        <div className="w-full rounded-2xl border border-border/60 bg-background/70 p-4 shadow-sm xl:w-[320px]">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">数据导出</p>
                    <p className="mt-1 text-sm font-medium text-foreground">当前累计 {resultCount} 条结构化结果</p>
                    <p className="mt-1 text-xs text-muted-foreground">{active ? "任务仍在运行，也可以先导出当前结果。" : "支持 CSV 与 Excel 两种格式，适合复盘、汇报和二次处理。"}</p>
                </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => onExport("csv")} disabled={exporting !== null} className="rounded-xl">
                    {exporting === "csv" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
                    导出 CSV
                </Button>
                <Button variant="outline" onClick={() => onExport("excel")} disabled={exporting !== null} className="rounded-xl">
                    {exporting === "excel" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
                    导出 Excel
                </Button>
            </div>
        </div>
    );
}

export function TaskDetailHeader({
    task,
    active,
    isRunning,
    isPaused,
    exportReady,
    canBackfill,
    backfilling,
    connected,
    lastMessageAt,
    controlling,
    exporting,
    onCopyTaskId,
    onCopyKeyword,
    onScrollResults,
    onBackfill,
    onPause,
    onResume,
    onStop,
    onExport,
    savingConcurrency,
    onConcurrencyChange,
}: {
    task: TaskOut;
    active: boolean;
    isRunning: boolean;
    isPaused: boolean;
    exportReady: boolean;
    canBackfill: boolean;
    backfilling: boolean;
    connected: boolean;
    lastMessageAt: number | null;
    controlling: "pause" | "resume" | "stop" | null;
    exporting: "csv" | "excel" | null;
    onCopyTaskId: () => void;
    onCopyKeyword: () => void;
    onScrollResults: () => void;
    onBackfill: () => void;
    onPause: () => void;
    onResume: () => void;
    onStop: () => void;
    onExport: (format: "csv" | "excel") => void;
    savingConcurrency?: boolean;
    onConcurrencyChange?: (n: number) => void;
}) {
    const platformMeta = getPlatformMeta(task.platform);
    const phase = getTaskPhase(task);
    const backfillSummary = getCommentBackfillSummary(task);
    const backfillPercent = getCommentBackfillPercent(task);

    return (
        <div className="rounded-[1.75rem] border border-border/60 bg-card/90 p-6 shadow-sm backdrop-blur-sm sm:p-8">
            <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0 flex-1 space-y-4">
                    <Link href="/tasks" className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground">
                        <ArrowLeft className="h-4 w-4" />
                        返回采集队列
                    </Link>
                    <div className="flex flex-wrap items-center gap-2">
                        <span className={cn("inline-flex rounded-full px-3 py-1 text-xs font-medium", platformMeta.badgeClass)}>{platformMeta.label}</span>
                        <Badge variant="secondary" className="rounded-full px-3 py-1">{getTaskKindLabel(task)}</Badge>
                        <TaskStatusBadge status={task.status} riskState={task.risk_state} />
                        {task.fetch_replies ? <Badge variant="secondary" className="rounded-full px-3 py-1">评论抓取开启</Badge> : null}
                    </div>
                    <div className="space-y-3">
                        <div className="flex items-start gap-3">
                            <div className="mt-1 rounded-2xl border border-border/60 bg-background/70 p-2 text-muted-foreground">
                                <Terminal className="h-5 w-5" />
                            </div>
                            <div className="min-w-0">
                                <h1 className="break-words text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{task.keyword}</h1>
                                <p className="mt-2 text-sm leading-6 text-muted-foreground">{phase}</p>
                            </div>
                        </div>
                        <p className="text-xs text-muted-foreground">任务 ID：<span className="font-mono text-foreground">{task.task_id}</span></p>
                        <div className="flex flex-wrap gap-2">
                            <Button variant="ghost" size="sm" className="rounded-xl" onClick={onCopyTaskId}>
                                <Copy className="mr-1.5 h-3.5 w-3.5" />
                                复制任务 ID
                            </Button>
                            <Button variant="ghost" size="sm" className="rounded-xl" onClick={onCopyKeyword}>
                                <Copy className="mr-1.5 h-3.5 w-3.5" />
                                复制关键词
                            </Button>
                            {exportReady ? (
                                <Button variant="ghost" size="sm" className="rounded-xl" onClick={onScrollResults}>
                                    查看结果区
                                </Button>
                            ) : null}
                        </div>
                    </div>
                </div>

                <div className="flex w-full flex-col gap-3 xl:max-w-[420px] xl:items-end">
                    <div className="flex flex-wrap gap-2 xl:justify-end">
                        {active ? (
                            <>
                                {isRunning ? (
                                    <Button variant="outline" onClick={onPause} disabled={controlling !== null} className="rounded-xl">
                                        {controlling === "pause" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Pause className="mr-1.5 h-3.5 w-3.5" />}
                                        暂停
                                    </Button>
                                ) : null}
                                {isPaused ? (
                                    <Button variant="outline" onClick={onResume} disabled={controlling !== null} className="rounded-xl">
                                        {controlling === "resume" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Play className="mr-1.5 h-3.5 w-3.5" />}
                                        继续
                                    </Button>
                                ) : null}
                                <Button variant="outline" onClick={onStop} disabled={controlling !== null} className="rounded-xl border-red-300 text-red-700 hover:bg-red-50 dark:border-red-500/30 dark:text-red-300 dark:hover:bg-red-500/10">
                                    {controlling === "stop" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <StopCircle className="mr-1.5 h-3.5 w-3.5" />}
                                    终止
                                </Button>
                            </>
                        ) : (
                            <>
                                {canBackfill ? (
                                    <TaskCommentBackfillButton
                                        variant="outline"
                                        className="rounded-xl"
                                        disabled={controlling !== null}
                                        loading={backfilling}
                                        onClick={onBackfill}
                                    />
                                ) : null}
                                <Button variant="outline" onClick={onResume} disabled={controlling !== null || backfilling} className="rounded-xl">
                                    {controlling === "resume" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="mr-1.5 h-3.5 w-3.5" />}
                                    继续爬取
                                </Button>
                            </>
                        )}
                    </div>
                    {exportReady ? <TaskExportPanel resultCount={task.result_count} active={active} exporting={exporting} onExport={onExport} /> : null}
                </div>
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {task.task_kind === "comment_backfill" ? (
                    <div className="rounded-[1.25rem] border border-border/60 bg-background/70 px-5 py-4 shadow-sm">
                        <p className="text-sm font-medium text-muted-foreground">补采进度</p>
                        <div className="mt-2 flex items-center gap-3">
                            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                                <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${backfillPercent}%` }} />
                            </div>
                            <span className="text-xl font-bold tabular-nums text-foreground">{backfillPercent}%</span>
                        </div>
                        <p className="mt-1.5 text-xs text-muted-foreground">{backfillSummary || `共 ${task.result_count} 条`}</p>
                    </div>
                ) : (
                    <SummaryCard
                        label="结果数量"
                        value={`${task.result_count}`}
                        hint="任务会持续抓取直到数据耗尽或被终止"
                    />
                )}
                <SummaryCard label="实时通道" value={task.status === "pending" ? `队列第 ${task.queue_position ?? "-"} 位` : connected ? "实时推送中" : "轮询模式"} hint={lastMessageAt ? `最近消息 ${new Date(lastMessageAt).toLocaleTimeString("zh-CN")}` : "等待首条消息"} />
                <SummaryCard label="创建时间" value={formatDateTime(task.created_at)} hint={task.finished_at ? `结束于 ${formatDateTime(task.finished_at)}` : "任务仍在进行中"} />
                {task.task_kind === "comment_backfill_group" && onConcurrencyChange ? (
                    <ConcurrencySelector
                        value={task.concurrency ?? 1}
                        saving={savingConcurrency ?? false}
                        active={active}
                        onChange={onConcurrencyChange}
                    />
                ) : (
                    <SummaryCard
                        label="任务模式"
                        value={getTaskModeLabel(task)}
                        hint={getTaskQueueLabel(task) || (task.task_kind === "comment_backfill" ? `来源文件 ${task.source_file_name ?? "--"}` : task.fetch_replies ? `评论深度 ${task.reply_depth}` : "仅采集结构化结果")}
                    />
                )}
            </div>
        </div>
    );
}
