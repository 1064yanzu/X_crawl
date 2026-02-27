"use client";
import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
    ArrowLeft,
    Database,
    FileDown,
    FileSpreadsheet,
    FileText,
    Loader2,
    Pause,
    Play,
    RotateCcw,
    StopCircle,
    Terminal,
} from "lucide-react";

import { api } from "@/services/api";
import { useTaskQuery } from "@/hooks/useTask";
import { TaskStreamEvent, useTaskStream } from "@/hooks/useTaskStream";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TweetCard } from "@/components/features/TweetCard";
import { LiveCrawlPreview } from "@/components/features/LiveCrawlPreview";
import { FailedRepliesPanel } from "@/components/features/FailedRepliesPanel";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { TaskStatusBadge } from "@/components/features/task-detail/TaskStatusBadge";
import { TaskAlerts } from "@/components/features/task-detail/TaskAlerts";
import { TaskRuntimeMetrics } from "@/components/features/task-detail/TaskRuntimeMetrics";
import { TaskLiveKpiBar } from "@/components/features/task-detail/TaskLiveKpiBar";
import { TaskLiveTimeline } from "@/components/features/task-detail/TaskLiveTimeline";
import { TaskLiveHealth } from "@/components/features/task-detail/TaskLiveHealth";
import { TaskCoverageRange } from "@/components/features/task-detail/TaskCoverageRange";
import { cn } from "@/lib/utils";

export default function TaskResultPage() {
    const { id } = useParams() as { id: string };
    const [exporting, setExporting] = React.useState<"csv" | "excel" | null>(null);
    const [controlling, setControlling] = React.useState<"pause" | "resume" | "stop" | null>(null);
    const [confirmStop, setConfirmStop] = React.useState(false);
    const { push } = useToast();
    const stream = useTaskStream(id, Boolean(id) && !controlling);
    const { data: polledTask, isLoading: loading, refetch } = useTaskQuery(
        id,
        Boolean(controlling),
        stream.fallbackPolling || !stream.task,
    );
    const task = stream.task ?? polledTask;
    const fallbackToastShown = React.useRef(false);

    React.useEffect(() => {
        if (stream.fallbackPolling && !fallbackToastShown.current) {
            push({ type: "info", title: "实时通道暂不可用，已自动回退轮询模式" });
            fallbackToastShown.current = true;
        }
        if (!stream.fallbackPolling) {
            fallbackToastShown.current = false;
        }
    }, [stream.fallbackPolling, push]);

    const handleExport = async (format: "csv" | "excel") => {
        if (!task) return;
        setExporting(format);
        try {
            if (format === "csv") await api.export.downloadCsv(task.task_id);
            else await api.export.downloadExcel(task.task_id);
        } catch (err) {
            console.error("导出失败:", err);
            push({ type: "error", title: "导出失败", description: err instanceof Error ? err.message : String(err) });
        } finally {
            setTimeout(() => setExporting(null), 1200);
        }
    };

    const handleControl = async (action: "pause" | "resume" | "stop") => {
        if (!task) return;
        setControlling(action);
        try {
            if (action === "pause") await api.tasks.pause(task.task_id);
            else if (action === "resume") await api.tasks.resume(task.task_id);
            else await api.tasks.stop(task.task_id);
            await refetch();
            push({
                type: "success",
                title: action === "pause" ? "任务已暂停" : action === "resume" ? "任务已恢复" : "终止信号已发送",
            });
        } catch (err) {
            console.error(`操作失败 (${action}):`, err);
            push({ type: "error", title: "任务控制失败", description: err instanceof Error ? err.message : String(err) });
        } finally {
            setControlling(null);
        }
    };

    if (loading && !task) {
        return (
            <div className="flex min-h-[50vh] flex-col items-center justify-center space-y-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="font-medium text-muted-foreground">正在获取采集队列状态...</p>
            </div>
        );
    }

    if (!task) {
        return (
            <div className="flex flex-col items-center rounded-2xl border bg-card py-24 text-center shadow-sm">
                <Database className="mb-6 h-16 w-16 text-muted-foreground/30" />
                <h2 className="mb-2 text-2xl font-bold">未找到采集记录</h2>
                <p className="mb-6 text-muted-foreground">该任务可能已被清理或不存在。</p>
                <Link href="/tasks">
                    <Button variant="outline">返回采集队列</Button>
                </Link>
            </div>
        );
    }

    const isRunning = task.status === "running" || task.status === "pending";
    const isPaused = task.status === "paused";
    const isRiskPaused = isPaused && task.risk_state !== "none";
    const isStopped = task.status === "stopped";
    const isActive = isRunning || isPaused;
    const hasLimit = task.max_count > 0;
    const progressPct = hasLimit ? Math.min(100, Math.round((task.result_count / task.max_count) * 100)) : 0;
    const finishedTweets = task.tweets ?? [];
    const latestActionEvent =
        task.latest_action && typeof task.latest_action.type === "string"
            ? (task.latest_action as unknown as TaskStreamEvent)
            : null;

    return (
        <div className="mx-auto max-w-5xl space-y-6 pb-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="flex items-center gap-4 border-b border-border/40 pb-2">
                <Link href="/tasks">
                    <Button variant="ghost" size="icon" className="h-9 w-9 rounded-md border shadow-sm hover:bg-muted">
                        <ArrowLeft className="h-4 w-4 text-muted-foreground" />
                    </Button>
                </Link>
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-3">
                        <Terminal className="h-5 w-5 shrink-0 text-muted-foreground" />
                        <h2 className="truncate font-mono text-xl font-bold tracking-tight sm:text-2xl">{task.keyword}</h2>
                        <Badge variant="outline" className="ml-2 hidden font-mono text-xs text-muted-foreground sm:inline-flex">
                            ID: {task.task_id.substring(0, 12)}
                        </Badge>
                    </div>
                </div>

                {isActive && (
                    <div className="flex shrink-0 items-center gap-2">
                        {isRunning && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleControl("pause")}
                                disabled={controlling !== null}
                                className="border-amber-300 text-amber-700 hover:bg-amber-50"
                            >
                                {controlling === "pause" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Pause className="mr-1.5 h-3.5 w-3.5" />}
                                暂停
                            </Button>
                        )}
                        {isPaused && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleControl("resume")}
                                disabled={controlling !== null}
                                className="border-blue-300 text-blue-700 hover:bg-blue-50"
                            >
                                {controlling === "resume" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Play className="mr-1.5 h-3.5 w-3.5" />}
                                继续
                            </Button>
                        )}
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setConfirmStop(true)}
                            disabled={controlling !== null}
                            className="border-red-300 text-red-700 hover:bg-red-50"
                        >
                            {controlling === "stop" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <StopCircle className="mr-1.5 h-3.5 w-3.5" />}
                            终止
                        </Button>
                    </div>
                )}

                {(task.status === "done" || isStopped || task.status === "failed") && (
                    <div className="flex shrink-0 items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleControl("resume")}
                            disabled={controlling !== null}
                            className="border-blue-300 text-blue-700 hover:bg-blue-50"
                        >
                            {controlling === "resume" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="mr-1.5 h-3.5 w-3.5" />}
                            继续爬取
                        </Button>
                        {task.result_count > 0 && (
                            <>
                                <Button variant="outline" size="sm" onClick={() => handleExport("csv")} disabled={exporting !== null}>
                                    {exporting === "csv" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <FileText className="mr-1.5 h-3.5 w-3.5" />}
                                    CSV
                                </Button>
                                <Button variant="outline" size="sm" onClick={() => handleExport("excel")} disabled={exporting !== null}>
                                    {exporting === "excel" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <FileSpreadsheet className="mr-1.5 h-3.5 w-3.5" />}
                                    Excel
                                </Button>
                                <FileDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                            </>
                        )}
                    </div>
                )}
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div className="bg-card border rounded-xl p-5 shadow-sm flex flex-col justify-center">
                    <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        当前运行状态
                    </p>
                    <div className="flex items-center gap-2">
                        <TaskStatusBadge status={task.status} riskState={task.risk_state} />
                    </div>
                </div>

                <div className="bg-card border rounded-xl p-5 shadow-sm flex flex-col justify-center">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">结构化数据提取量</p>
                    <div className="mb-2 flex items-baseline gap-2">
                        <span className="text-3xl font-bold font-mono">{task.result_count}</span>
                        {hasLimit ? <span className="text-sm text-muted-foreground">/ {task.max_count} 条</span> : <span className="text-sm text-muted-foreground">条（无上限）</span>}
                    </div>
                    {hasLimit ? (
                        <>
                            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                                <div className={cn("h-full rounded-full transition-all duration-500", task.status === "done" ? "bg-green-500" : "bg-blue-500")} style={{ width: `${progressPct}%` }} />
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">{progressPct}% {isActive && task.current_page > 0 ? `· 已完成第 ${task.current_page} 页` : ""}</p>
                        </>
                    ) : (
                        <p className="mt-1 text-xs text-muted-foreground">{isActive && task.current_page > 0 ? `已完成第 ${task.current_page} 页` : "持续采集中，直到数据耗尽或手动终止"}</p>
                    )}
                </div>

                <TaskRuntimeMetrics qualityState={task.quality_state} runtimeMetrics={task.runtime_metrics} />
            </div>

            <TaskAlerts error={task.error} isRiskPaused={isRiskPaused} debugScreenshot={task.debug_screenshot} />

            {isActive && (
                <div className="space-y-3">
                    <TaskLiveKpiBar task={task} connected={stream.connected} />
                    <TaskLiveHealth task={task} />
                    <TaskCoverageRange task={task} />
                    <TaskLiveTimeline
                        events={
                            stream.events.length > 0
                                ? stream.events
                                : latestActionEvent
                                    ? [latestActionEvent]
                                    : []
                        }
                    />
                </div>
            )}

            {!isActive && task.result_count > 0 && <TaskCoverageRange task={task} />}

            {task.fetch_replies && <FailedRepliesPanel taskId={task.task_id} taskStatus={task.status} />}

            <div className="pt-4">
                <div className="mb-6 flex items-center justify-between">
                    <h3 className="flex items-center gap-2 text-lg font-bold">
                        <Database className="h-5 w-5 text-primary" />
                        {isActive ? "实时数据流" : "采集结果"}
                    </h3>

                    {task.result_count > 0 && task.status !== "done" && (
                        <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">导出已抓取数据:</span>
                            <Button variant="ghost" size="sm" onClick={() => handleExport("csv")} disabled={exporting !== null} className="h-7 text-xs">
                                CSV
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => handleExport("excel")} disabled={exporting !== null} className="h-7 text-xs">
                                Excel
                            </Button>
                        </div>
                    )}
                </div>

                {isActive && <LiveCrawlPreview task={task} />}

                {!isActive &&
                    (finishedTweets.length === 0 ? (
                        <div className="flex flex-col items-center rounded-2xl border border-dashed bg-muted/20 py-20 text-center">
                            <Database className="mb-4 h-12 w-12 text-muted-foreground/30" />
                            <p className="font-medium text-muted-foreground">此次任务未命中有效结构化记录</p>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {finishedTweets.map((tweet: Record<string, unknown>, index: number) => (
                                <TweetCard key={`${(tweet.id as string) || task.task_id}-${index}`} tweet={tweet} />
                            ))}
                        </div>
                    ))}
            </div>

            <ConfirmDialog
                open={confirmStop}
                title="确认终止该任务？"
                description="已抓取的数据会保留，任务状态将变为已终止。"
                confirmText="终止任务"
                cancelText="取消"
                onCancel={() => setConfirmStop(false)}
                onConfirm={async () => {
                    setConfirmStop(false);
                    await handleControl("stop");
                }}
            />
        </div>
    );
}
