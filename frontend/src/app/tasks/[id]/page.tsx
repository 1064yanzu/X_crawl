"use client";
import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
    ArrowLeft,
    ChevronLeft,
    ChevronRight,
    Copy,
    Database,
    FileSpreadsheet,
    FileText,
    Loader2,
    Pause,
    Play,
    RotateCcw,
    Search,
    StopCircle,
    Terminal,
} from "lucide-react";
import { api } from "@/services/api";
import { useTaskQuery } from "@/hooks/useTask";
import { TaskStreamEvent, useTaskStream } from "@/hooks/useTaskStream";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { TweetCard } from "@/components/features/TweetCard";
import { LiveCrawlPreview } from "@/components/features/LiveCrawlPreview";
import { FailedRepliesPanel } from "@/components/features/FailedRepliesPanel";
import { TaskStatusBadge } from "@/components/features/task-detail/TaskStatusBadge";
import { TaskAlerts } from "@/components/features/task-detail/TaskAlerts";
import { TaskRuntimeMetrics } from "@/components/features/task-detail/TaskRuntimeMetrics";
import { TaskLiveKpiBar } from "@/components/features/task-detail/TaskLiveKpiBar";
import { TaskLiveTimeline } from "@/components/features/task-detail/TaskLiveTimeline";
import { TaskLiveHealth } from "@/components/features/task-detail/TaskLiveHealth";
import { TaskCoverageRange } from "@/components/features/task-detail/TaskCoverageRange";
import { TaskSegmentProgress } from "@/components/features/task-detail/TaskSegmentProgress";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { getPlatformMeta } from "@/lib/platformRegistry";
import { cn } from "@/lib/utils";
import { formatDateTime, getTaskPhase, isTaskActive } from "@/lib/task-ui";

type ResultFilter = "all" | "media" | "replies" | "links";
type ResultSort = "newest" | "oldest" | "likes" | "engagement";
type ResultDensity = "comfortable" | "compact";
type TweetRecord = Record<string, unknown>;

const RESULT_FILTER_OPTIONS: Array<{ value: ResultFilter; label: string }> = [
    { value: "all", label: "全部结果" },
    { value: "media", label: "带媒体" },
    { value: "replies", label: "带回复" },
    { value: "links", label: "带外链" },
];

export default function TaskResultPage() {
    const { id } = useParams() as { id: string };
    const [exporting, setExporting] = React.useState<"csv" | "excel" | null>(null);
    const [controlling, setControlling] = React.useState<"pause" | "resume" | "stop" | null>(null);
    const [confirmStop, setConfirmStop] = React.useState(false);
    const [resultQuery, setResultQuery] = React.useState("");
    const [resultFilter, setResultFilter] = React.useState<ResultFilter>("all");
    const [resultSort, setResultSort] = React.useState<ResultSort>("newest");
    const [resultPage, setResultPage] = React.useState(1);
    const [resultPageSize, setResultPageSize] = React.useState(10);
    const [resultPageInput, setResultPageInput] = React.useState("1");
    const [resultDensity, setResultDensity] = React.useState<ResultDensity>("comfortable");
    const { push } = useToast();
    const stream = useTaskStream(id, Boolean(id) && !controlling);
    const { data: polledTask, isLoading, refetch } = useTaskQuery(
        id,
        Boolean(controlling),
        stream.fallbackPolling || !stream.task,
    );
    const task = stream.task ?? polledTask;
    const fallbackToastShown = React.useRef(false);
    const finishedTweets = React.useMemo(() => ((task?.tweets ?? []) as TweetRecord[]), [task]);
    const normalizedResultQuery = resultQuery.trim().toLowerCase();

    React.useEffect(() => {
        if (stream.fallbackPolling && !fallbackToastShown.current) {
            push({ type: "info", title: "实时通道暂不可用，已自动回退到轮询模式" });
            fallbackToastShown.current = true;
        }
        if (!stream.fallbackPolling) {
            fallbackToastShown.current = false;
        }
    }, [stream.fallbackPolling, push]);

    const filteredFinishedTweets = React.useMemo(() => {
        const matched = finishedTweets.filter((tweet) => {
            if (!matchesResultFilter(tweet, resultFilter)) return false;
            if (!normalizedResultQuery) return true;
            return buildTweetSearchText(tweet).includes(normalizedResultQuery);
        });

        const sorted = [...matched];
        sorted.sort((left, right) => {
            if (resultSort === "oldest") return getTweetTimestamp(left) - getTweetTimestamp(right);
            if (resultSort === "likes") return getTweetMetric(right, "likes") - getTweetMetric(left, "likes");
            if (resultSort === "engagement") return getTweetEngagement(right) - getTweetEngagement(left);
            return getTweetTimestamp(right) - getTweetTimestamp(left);
        });
        return sorted;
    }, [finishedTweets, normalizedResultQuery, resultFilter, resultSort]);

    const resultStats = React.useMemo(() => {
        return finishedTweets.reduce<{ media: number; replies: number; links: number }>(
            (acc, tweet) => {
                if (getTweetMediaCount(tweet) > 0) acc.media += 1;
                if (getTweetReplyCount(tweet) > 0) acc.replies += 1;
                if (getTweetLinkCount(tweet) > 0) acc.links += 1;
                return acc;
            },
            { media: 0, replies: 0, links: 0 },
        );
    }, [finishedTweets]);

    React.useEffect(() => {
        if (typeof window === "undefined") return;
        const savedPageSize = window.localStorage.getItem("task-result-page-size");
        const parsed = savedPageSize ? Number(savedPageSize) : Number.NaN;
        if ([10, 20, 50].includes(parsed)) {
            setResultPageSize(parsed);
        }

        const savedDensity = window.localStorage.getItem("task-result-density");
        if (savedDensity === "comfortable" || savedDensity === "compact") {
            setResultDensity(savedDensity);
        }
    }, []);

    React.useEffect(() => {
        if (typeof window === "undefined") return;
        window.localStorage.setItem("task-result-page-size", String(resultPageSize));
    }, [resultPageSize]);

    React.useEffect(() => {
        if (typeof window === "undefined") return;
        window.localStorage.setItem("task-result-density", resultDensity);
    }, [resultDensity]);

    React.useEffect(() => {
        setResultPage(1);
    }, [normalizedResultQuery, resultFilter, resultSort, resultPageSize, task?.task_id]);

    const totalResultPages = Math.max(1, Math.ceil(filteredFinishedTweets.length / resultPageSize));
    const visibleResultPage = Math.min(resultPage, totalResultPages);

    React.useEffect(() => {
        if (resultPage > totalResultPages) {
            setResultPage(totalResultPages);
        }
    }, [resultPage, totalResultPages]);

    React.useEffect(() => {
        setResultPageInput(String(visibleResultPage));
    }, [visibleResultPage]);

    const paginatedFinishedTweets = React.useMemo(() => {
        const start = (visibleResultPage - 1) * resultPageSize;
        return filteredFinishedTweets.slice(start, start + resultPageSize);
    }, [filteredFinishedTweets, resultPageSize, visibleResultPage]);

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
            setTimeout(() => setExporting(null), 800);
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
                title: action === "pause" ? "任务已暂停" : action === "resume" ? "任务已恢复" : "终止指令已发送",
            });
        } catch (err) {
            console.error(`操作失败 (${action}):`, err);
            push({ type: "error", title: "任务控制失败", description: err instanceof Error ? err.message : String(err) });
        } finally {
            setControlling(null);
        }
    };

    const goToResultPage = React.useCallback((page: number) => {
        setResultPage(Math.max(1, Math.min(totalResultPages, page)));
    }, [totalResultPages]);

    const copyText = React.useCallback(async (label: string, value: string) => {
        if (typeof navigator === "undefined" || !navigator.clipboard) {
            push({ type: "error", title: "当前环境不支持复制" });
            return;
        }
        try {
            await navigator.clipboard.writeText(value);
            push({ type: "success", title: `已复制${label}` });
        } catch (err) {
            console.error("复制失败:", err);
            push({ type: "error", title: `复制${label}失败` });
        }
    }, [push]);

    const scrollToResults = React.useCallback(() => {
        const element = document.getElementById("task-results");
        if (!element) return;
        element.scrollIntoView({ behavior: "smooth", block: "start" });
    }, []);

    if (isLoading && !task) {
        return (
            <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="font-medium text-muted-foreground">正在加载任务详情...</p>
            </div>
        );
    }

    if (!task) {
        return (
            <EmptyState
                icon={Database}
                title="未找到采集记录"
                description="该任务可能已被清理、删除，或当前地址无效。"
                action={
                    <Link href="/tasks">
                        <Button variant="outline" className="rounded-xl">返回采集队列</Button>
                    </Link>
                }
            />
        );
    }

    const isRunning = task.status === "running" || task.status === "pending";
    const isPaused = task.status === "paused";
    const isRiskPaused = isPaused && task.risk_state !== "none";
    const active = isTaskActive(task.status);
    const hasLimit = task.max_count > 0;
    const progressPct = hasLimit ? Math.min(100, Math.round((task.result_count / task.max_count) * 100)) : 0;
    const latestActionEvent = task.latest_action && typeof task.latest_action.type === "string"
        ? (task.latest_action as unknown as TaskStreamEvent)
        : null;
    const platformMeta = getPlatformMeta(task.platform);
    const phase = getTaskPhase(task);
    const exportReady = task.result_count > 0;

    return (
        <div className="mx-auto max-w-6xl space-y-6 pb-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="rounded-[1.75rem] border border-border/60 bg-card/90 p-6 shadow-sm backdrop-blur-sm sm:p-8">
                <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0 flex-1 space-y-4">
                        <Link href="/tasks" className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground">
                            <ArrowLeft className="h-4 w-4" />
                            返回采集队列
                        </Link>
                        <div className="flex flex-wrap items-center gap-2">
                            <span className={cn("inline-flex rounded-full px-3 py-1 text-xs font-medium", platformMeta.badgeClass)}>{platformMeta.label}</span>
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
                                <Button variant="ghost" size="sm" className="rounded-xl" onClick={() => void copyText("任务 ID", task.task_id)}>
                                    <Copy className="mr-1.5 h-3.5 w-3.5" />
                                    复制任务 ID
                                </Button>
                                <Button variant="ghost" size="sm" className="rounded-xl" onClick={() => void copyText("关键词", task.keyword)}>
                                    <Copy className="mr-1.5 h-3.5 w-3.5" />
                                    复制关键词
                                </Button>
                                {exportReady ? (
                                    <Button variant="ghost" size="sm" className="rounded-xl" onClick={scrollToResults}>
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
                                        <Button variant="outline" onClick={() => void handleControl("pause")} disabled={controlling !== null} className="rounded-xl">
                                            {controlling === "pause" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Pause className="mr-1.5 h-3.5 w-3.5" />}
                                            暂停
                                        </Button>
                                    ) : null}
                                    {isPaused ? (
                                        <Button variant="outline" onClick={() => void handleControl("resume")} disabled={controlling !== null} className="rounded-xl">
                                            {controlling === "resume" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Play className="mr-1.5 h-3.5 w-3.5" />}
                                            继续
                                        </Button>
                                    ) : null}
                                    <Button variant="outline" onClick={() => setConfirmStop(true)} disabled={controlling !== null} className="rounded-xl border-red-300 text-red-700 hover:bg-red-50 dark:border-red-500/30 dark:text-red-300 dark:hover:bg-red-500/10">
                                        {controlling === "stop" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <StopCircle className="mr-1.5 h-3.5 w-3.5" />}
                                        终止
                                    </Button>
                                </>
                            ) : (
                                <Button variant="outline" onClick={() => void handleControl("resume")} disabled={controlling !== null} className="rounded-xl">
                                    {controlling === "resume" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="mr-1.5 h-3.5 w-3.5" />}
                                    继续爬取
                                </Button>
                            )}
                        </div>
                        {exportReady ? (
                            <TaskExportPanel
                                resultCount={task.result_count}
                                active={active}
                                exporting={exporting}
                                onExport={(format) => void handleExport(format)}
                            />
                        ) : null}
                    </div>
                </div>

                <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <SummaryCard label="结果数量" value={hasLimit ? `${task.result_count} / ${task.max_count}` : `${task.result_count}`} hint={hasLimit ? `完成度 ${progressPct}%` : "未设置数量上限"} />
                    <SummaryCard label="实时通道" value={task.status === "pending" ? `队列第 ${task.queue_position ?? "-"} 位` : stream.connected ? "实时推送中" : "轮询模式"} hint={stream.lastMessageAt ? `最近消息 ${new Date(stream.lastMessageAt).toLocaleTimeString("zh-CN")}` : "等待首条消息"} />
                    <SummaryCard label="创建时间" value={formatDateTime(task.created_at)} hint={task.finished_at ? `结束于 ${formatDateTime(task.finished_at)}` : "任务仍在进行中"} />
                    <SummaryCard label="任务模式" value={task.product} hint={task.fetch_replies ? `评论深度 ${task.reply_depth}` : "仅采集结构化结果"} />
                </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-2xl border bg-card p-5 shadow-sm">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">当前状态</p>
                    <TaskStatusBadge status={task.status} riskState={task.risk_state} />
                </div>

                <div className="rounded-2xl border bg-card p-5 shadow-sm">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">采集进度</p>
                    <div className="mb-2 flex items-baseline gap-2">
                        <span className="text-3xl font-semibold font-mono">{task.result_count}</span>
                        {hasLimit ? <span className="text-sm text-muted-foreground">/ {task.max_count} 条</span> : <span className="text-sm text-muted-foreground">条（不限）</span>}
                    </div>
                    {hasLimit ? (
                        <>
                            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                                <div className={cn("h-full rounded-full transition-all duration-500", task.status === "done" ? "bg-emerald-500" : "bg-blue-500")} style={{ width: `${progressPct}%` }} />
                            </div>
                            <p className="mt-2 text-xs text-muted-foreground">{progressPct}% {active && task.current_page > 0 ? `· 已完成第 ${task.current_page} 页` : ""}</p>
                        </>
                    ) : (
                        <p className="text-sm text-muted-foreground">{active && task.current_page > 0 ? `当前已抓到第 ${task.current_page} 页` : "会持续采集直到数据耗尽或被终止。"}</p>
                    )}
                </div>

                <TaskRuntimeMetrics qualityState={task.quality_state} runtimeMetrics={task.runtime_metrics} />
            </div>

            <TaskAlerts error={task.error} isRiskPaused={isRiskPaused} debugScreenshot={task.debug_screenshot} />

            {active ? (
                <div className="space-y-3">
                    <TaskLiveKpiBar task={task} connected={stream.connected} />
                    <TaskSegmentProgress task={task} />
                    <TaskLiveHealth task={task} />
                    <TaskCoverageRange task={task} />
                    <TaskLiveTimeline
                        events={stream.events.length > 0 ? stream.events : latestActionEvent ? [latestActionEvent] : []}
                    />
                </div>
            ) : task.result_count > 0 ? (
                <div className="space-y-3">
                    <TaskSegmentProgress task={task} />
                    <TaskCoverageRange task={task} />
                </div>
            ) : null}

            {task.fetch_replies ? <FailedRepliesPanel taskId={task.task_id} taskStatus={task.status} /> : null}

            <Card id="task-results" className="rounded-[1.5rem] border-border/60 bg-card/90 p-5 shadow-sm sm:p-6">
                <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <h3 className="flex items-center gap-2 text-lg font-semibold">
                            <Database className="h-5 w-5 text-primary" />
                            {active ? "实时数据流" : "采集结果"}
                        </h3>
                        <p className="mt-1 text-sm text-muted-foreground">{active ? "任务仍在运行，下面展示实时预览。" : "任务已结束，下面展示最终结构化结果。"}</p>
                    </div>
                    {exportReady ? (
                        <div className="rounded-2xl border border-dashed border-border/60 bg-background/60 px-3 py-2 text-xs text-muted-foreground">
                            导出入口已收纳到顶部操作区；{active ? "任务运行中也可以先下载当前结果。" : "可直接下载 CSV 或 Excel 做复盘与分发。"}
                        </div>
                    ) : null}
                </div>

                {active ? <LiveCrawlPreview task={task} /> : null}

                {!active ? (
                    finishedTweets.length === 0 ? (
                        <EmptyState
                            icon={Database}
                            title="此次任务没有结构化结果"
                            description="可能未命中搜索条件，或任务在结构化输出前已经中止。"
                            className="py-20"
                        />
                    ) : (
                        <div className="space-y-5">
                            <div className="rounded-[1.25rem] border border-border/60 bg-background/70 p-4 shadow-sm">
                                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                    <div className="space-y-3">
                                        <div>
                                            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">结果检索</p>
                                            <p className="mt-1 text-sm text-foreground">共 {finishedTweets.length} 条结果，筛出 {filteredFinishedTweets.length} 条，当前第 {visibleResultPage} / {totalResultPages} 页</p>
                                        </div>
                                        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                                            <span className="rounded-full bg-muted px-2.5 py-1">带媒体 {resultStats.media}</span>
                                            <span className="rounded-full bg-muted px-2.5 py-1">带回复 {resultStats.replies}</span>
                                            <span className="rounded-full bg-muted px-2.5 py-1">带外链 {resultStats.links}</span>
                                        </div>
                                    </div>
                                    <div className="grid w-full gap-3 xl:max-w-4xl xl:grid-cols-[minmax(0,1fr)_220px_160px_auto]">
                                        <div className="relative">
                                            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                            <input
                                                type="text"
                                                value={resultQuery}
                                                onChange={(event) => setResultQuery(event.target.value)}
                                                placeholder="搜索正文、作者、用户名或标签"
                                                className="h-11 w-full rounded-xl border border-input bg-background pl-10 pr-4 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                            />
                                        </div>
                                        <select
                                            value={resultSort}
                                            onChange={(event) => setResultSort(event.target.value as ResultSort)}
                                            className="h-11 rounded-xl border border-border/60 bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                        >
                                            <option value="newest">按发布时间（最新）</option>
                                            <option value="oldest">按发布时间（最早）</option>
                                            <option value="likes">按点赞数</option>
                                            <option value="engagement">按互动总量</option>
                                        </select>
                                        <select
                                            value={resultPageSize}
                                            onChange={(event) => setResultPageSize(Number(event.target.value))}
                                            className="h-11 rounded-xl border border-border/60 bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                        >
                                            <option value={10}>每页 10 条</option>
                                            <option value={20}>每页 20 条</option>
                                            <option value={50}>每页 50 条</option>
                                        </select>
                                        <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-background p-1 shadow-sm">
                                            <Button
                                                type="button"
                                                variant={resultDensity === "comfortable" ? "default" : "ghost"}
                                                size="sm"
                                                className="rounded-lg"
                                                onClick={() => setResultDensity("comfortable")}
                                            >
                                                舒展阅读
                                            </Button>
                                            <Button
                                                type="button"
                                                variant={resultDensity === "compact" ? "default" : "ghost"}
                                                size="sm"
                                                className="rounded-lg"
                                                onClick={() => setResultDensity("compact")}
                                            >
                                                紧凑阅读
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-3 flex flex-wrap gap-2">
                                    {RESULT_FILTER_OPTIONS.map((option) => (
                                        <Button
                                            key={option.value}
                                            variant="outline"
                                            size="sm"
                                            className={cn("rounded-full", resultFilter === option.value && "border-primary bg-primary/8 text-primary")}
                                            onClick={() => setResultFilter(option.value)}
                                        >
                                            {option.label}
                                        </Button>
                                    ))}
                                    {(resultQuery || resultFilter !== "all" || resultSort !== "newest") ? (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="rounded-full"
                                            onClick={() => {
                                                setResultQuery("");
                                                setResultFilter("all");
                                                setResultSort("newest");
                                            }}
                                        >
                                            重置条件
                                        </Button>
                                    ) : null}
                                </div>
                            </div>

                            {filteredFinishedTweets.length === 0 ? (
                                <EmptyState
                                    icon={Search}
                                    title="没有匹配当前条件的结果"
                                    description="可以换个关键词、切换筛选标签，或恢复默认排序后再试。"
                                    action={<Button variant="outline" className="rounded-xl" onClick={() => {
                                        setResultQuery("");
                                        setResultFilter("all");
                                        setResultSort("newest");
                                    }}>重置结果筛选</Button>}
                                />
                            ) : (
                                <div className="space-y-4">
                                    <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-muted/20 px-4 py-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                                        <div>
                                            当前显示第 <span className="font-medium text-foreground">{visibleResultPage}</span> / <span className="font-medium text-foreground">{totalResultPages}</span> 页，每页 <span className="font-medium text-foreground">{resultPageSize}</span> 条。
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="rounded-xl"
                                                onClick={() => goToResultPage(1)}
                                                disabled={visibleResultPage <= 1}
                                            >
                                                首页
                                            </Button>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="rounded-xl"
                                                onClick={() => goToResultPage(visibleResultPage - 1)}
                                                disabled={visibleResultPage <= 1}
                                            >
                                                <ChevronLeft className="mr-1.5 h-3.5 w-3.5" />
                                                上一页
                                            </Button>
                                            <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-background px-2 py-1.5">
                                                <input
                                                    type="number"
                                                    min={1}
                                                    max={totalResultPages}
                                                    value={resultPageInput}
                                                    onChange={(event) => setResultPageInput(event.target.value)}
                                                    className="w-16 bg-transparent text-center text-sm focus:outline-none"
                                                />
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="rounded-lg px-2"
                                                    onClick={() => {
                                                        const parsed = Number(resultPageInput);
                                                        if (Number.isFinite(parsed)) goToResultPage(parsed);
                                                    }}
                                                >
                                                    跳转
                                                </Button>
                                            </div>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="rounded-xl"
                                                onClick={() => goToResultPage(visibleResultPage + 1)}
                                                disabled={visibleResultPage >= totalResultPages}
                                            >
                                                下一页
                                                <ChevronRight className="ml-1.5 h-3.5 w-3.5" />
                                            </Button>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="rounded-xl"
                                                onClick={() => goToResultPage(totalResultPages)}
                                                disabled={visibleResultPage >= totalResultPages}
                                            >
                                                末页
                                            </Button>
                                        </div>
                                    </div>
                                    {paginatedFinishedTweets.map((tweet, index) => (
                                        <TweetCard
                                            key={`${(tweet.id as string) || task.task_id}-${visibleResultPage}-${index}`}
                                            tweet={tweet}
                                            compact={resultDensity === "compact"}
                                        />
                                    ))}
                                </div>
                            )}
                        </div>
                    )
                ) : null}
            </Card>

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
                    {exporting === "csv" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <FileText className="mr-1.5 h-3.5 w-3.5" />}
                    导出 CSV
                </Button>
                <Button variant="outline" onClick={() => onExport("excel")} disabled={exporting !== null} className="rounded-xl">
                    {exporting === "excel" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <FileSpreadsheet className="mr-1.5 h-3.5 w-3.5" />}
                    导出 Excel
                </Button>
            </div>
        </div>
    );
}

function SummaryCard({ label, value, hint }: { label: string; value: string; hint: string }) {
    return (
        <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-4 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
            <p className="mt-2 text-lg font-semibold text-foreground">{value}</p>
            <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
        </div>
    );
}

function matchesResultFilter(tweet: TweetRecord, filter: ResultFilter) {
    if (filter === "media") return getTweetMediaCount(tweet) > 0;
    if (filter === "replies") return getTweetReplyCount(tweet) > 0;
    if (filter === "links") return getTweetLinkCount(tweet) > 0;
    return true;
}

function buildTweetSearchText(tweet: TweetRecord) {
    const author = getTweetAuthor(tweet);
    return [
        typeof tweet.text === "string" ? tweet.text : "",
        typeof author.name === "string" ? author.name : "",
        typeof author.screen_name === "string" ? author.screen_name : "",
        ...getTweetHashtags(tweet),
    ]
        .join(" ")
        .toLowerCase();
}

function getTweetAuthor(tweet: TweetRecord) {
    const author = tweet.author;
    return author && typeof author === "object" ? (author as TweetRecord) : {};
}

function getTweetHashtags(tweet: TweetRecord) {
    if (!Array.isArray(tweet.hashtags)) return [] as string[];
    return tweet.hashtags.filter((item): item is string => typeof item === "string");
}

function getTweetMediaCount(tweet: TweetRecord) {
    return Array.isArray(tweet.media) ? tweet.media.length : 0;
}

function getTweetReplyCount(tweet: TweetRecord) {
    return Array.isArray(tweet.replies) ? tweet.replies.length : 0;
}

function getTweetLinkCount(tweet: TweetRecord) {
    return Array.isArray(tweet.urls) ? tweet.urls.length : 0;
}

function getTweetTimestamp(tweet: TweetRecord) {
    const createdAt = typeof tweet.created_at === "string" ? Date.parse(tweet.created_at) : Number.NaN;
    return Number.isNaN(createdAt) ? 0 : createdAt;
}

function getTweetMetric(tweet: TweetRecord, key: string) {
    const metrics = tweet.metrics;
    if (!metrics || typeof metrics !== "object") return 0;
    const value = (metrics as Record<string, unknown>)[key];
    return typeof value === "number" ? value : 0;
}

function getTweetEngagement(tweet: TweetRecord) {
    return getTweetMetric(tweet, "likes") + getTweetMetric(tweet, "retweets") + getTweetMetric(tweet, "replies") + getTweetMetric(tweet, "bookmarks");
}
