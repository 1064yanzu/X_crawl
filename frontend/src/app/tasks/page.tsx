"use client";
import * as React from "react";
import Link from "next/link";
import { api } from "@/services/api";
import {
    TerminalSquare,
    Search,
    Trash2,
    Clock,
    CheckCircle2,
    XCircle,
    Loader2,
    Database,
    RotateCcw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useTasksQuery } from "@/hooks/useTasks";
import { useToast } from "@/components/ui/toast";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PlatformTabs } from "@/components/ui/platform-tabs";
import {
    getPlatformsWithAll,
    getPlatformMeta,
} from "@/lib/platformRegistry";

function rangeText(range: Record<string, unknown> | undefined): string {
    if (!range) return "--";
    const start =
        typeof range.combined_start_at === "string" ? range.combined_start_at : "";
    const end =
        typeof range.combined_end_at === "string" ? range.combined_end_at : "";
    if (!start || !end) return "--";
    return `${new Date(start).toLocaleDateString()} ~ ${new Date(end).toLocaleDateString()}`;
}

export default function TasksPage() {
    const { data, isLoading, refetch } = useTasksQuery(5000);
    const tasks = React.useMemo(() => data ?? [], [data]);
    const loading = isLoading;
    const { push } = useToast();
    const [resumingId, setResumingId] = React.useState<string | null>(null);
    const [deleteId, setDeleteId] = React.useState<string | null>(null);
    const [activePlatform, setActivePlatform] = React.useState("all");

    const handleDelete = async (taskId: string) => {
        try {
            await api.tasks.delete(taskId);
            push({ type: "success", title: "任务已删除" });
            await refetch();
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "删除任务失败" });
        }
    };

    const handleResume = async (taskId: string) => {
        setResumingId(taskId);
        try {
            await api.tasks.resume(taskId);
            push({ type: "success", title: "任务已加入调度队列" });
            await refetch();
        } catch (err) {
            console.error(err);
            push({
                type: "error",
                title: "恢复任务失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setResumingId(null);
        }
    };

    // 按平台过滤
    const filteredTasks = React.useMemo(() => {
        if (activePlatform === "all") return tasks;
        return tasks.filter((t) => (t.platform ?? "x") === activePlatform);
    }, [tasks, activePlatform]);

    // 各平台计数
    const platformCounts = React.useMemo(() => {
        const counts: Record<string, number> = { all: tasks.length };
        for (const t of tasks) {
            const p = t.platform ?? "x";
            counts[p] = (counts[p] ?? 0) + 1;
        }
        return counts;
    }, [tasks]);

    const getStatusIndicator = (status: string) => {
        switch (status) {
            case "running":
                return (
                    <Badge
                        variant="secondary"
                        className="bg-blue-500/10 text-blue-600 hover:bg-blue-500/20"
                    >
                        <Loader2 className="w-3 h-3 mr-1 animate-spin" /> 采集中
                    </Badge>
                );
            case "done":
                return (
                    <Badge
                        variant="secondary"
                        className="bg-green-500/10 text-green-600 hover:bg-green-500/20"
                    >
                        <CheckCircle2 className="w-3 h-3 mr-1" /> 已完成
                    </Badge>
                );
            case "failed":
                return (
                    <Badge
                        variant="secondary"
                        className="bg-red-500/10 text-red-600 hover:bg-red-500/20"
                    >
                        <XCircle className="w-3 h-3 mr-1" /> 失败
                    </Badge>
                );
            case "paused":
                return (
                    <Badge
                        variant="secondary"
                        className="bg-amber-500/10 text-amber-600 hover:bg-amber-500/20"
                    >
                        已暂停
                    </Badge>
                );
            default:
                return (
                    <Badge variant="outline" className="text-gray-500">
                        等待中
                    </Badge>
                );
        }
    };

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out max-w-5xl mx-auto">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-border/40 pb-6">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight mb-2 flex items-center gap-2">
                        <Database className="w-7 h-7 text-primary" />
                        采集队列
                    </h2>
                    <p className="text-muted-foreground">
                        管理并监控后台运行的爬虫实例及已存档的抓取数据。
                    </p>
                </div>
                <Link href="/">
                    <Button variant="default" className="shadow-sm">
                        <TerminalSquare className="w-4 h-4 mr-2" /> 新建采集任务
                    </Button>
                </Link>
            </div>

            {/* 平台 Tab 切换 */}
            <PlatformTabs
                platforms={getPlatformsWithAll()}
                value={activePlatform}
                onChange={setActivePlatform}
                counts={platformCounts}
            />

            {loading && tasks.length === 0 ? (
                <div className="space-y-4 pt-4">
                    {[1, 2, 3].map((i) => (
                        <div
                            key={i}
                            className="h-24 bg-card animate-pulse rounded-xl border"
                        />
                    ))}
                </div>
            ) : filteredTasks.length === 0 ? (
                <Card className="flex flex-col items-center justify-center py-24 text-center border-dashed rounded-2xl mt-8 bg-muted/20 shadow-none">
                    <Database className="w-12 h-12 text-muted-foreground/30 mb-4" />
                    <h3 className="text-lg font-medium text-muted-foreground">
                        {activePlatform === "all"
                            ? "当前暂无采集任务"
                            : `当前暂无 ${getPlatformMeta(activePlatform).label} 采集任务`}
                    </h3>
                    {activePlatform !== "all" && tasks.length > 0 && (
                        <Button
                            variant="ghost"
                            className="mt-3 text-sm"
                            onClick={() => setActivePlatform("all")}
                        >
                            查看全部平台任务
                        </Button>
                    )}
                    {tasks.length === 0 && (
                        <Link href="/" className="mt-6">
                            <Button variant="outline">返回控制台新建</Button>
                        </Link>
                    )}
                </Card>
            ) : (
                <div className="grid gap-3 pt-2">
                    {filteredTasks.map((task) => {
                        const pm = getPlatformMeta(task.platform);
                        return (
                            <Card
                                key={task.task_id}
                                className="group transition-all duration-200 flex flex-col sm:flex-row rounded-xl shadow-sm hover:shadow-md cursor-pointer overflow-hidden border relative"
                            >
                                {/* 平台色条指示器 */}
                                <div
                                    className={cn(
                                        "absolute left-0 top-0 bottom-0 w-1 rounded-l-xl",
                                        pm.barClass
                                    )}
                                />

                                <Link
                                    href={`/tasks/${task.task_id}`}
                                    className="flex-1 p-4 pl-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                                >
                                    <div className="flex flex-col gap-2">
                                        <div className="flex items-center gap-2">
                                            <code className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded font-mono">
                                                {task.task_id.substring(0, 8)}
                                            </code>
                                            {getStatusIndicator(task.status)}
                                            <span
                                                className={cn(
                                                    "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                                                    pm.badgeClass
                                                )}
                                            >
                                                {pm.label}
                                            </span>
                                        </div>
                                        <div className="font-bold text-lg text-foreground line-clamp-1 flex items-center gap-2">
                                            <Search className="w-4 h-4 text-muted-foreground" />
                                            {task.keyword}
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-6 text-sm">
                                        <div className="flex flex-col items-end">
                                            <span className="text-muted-foreground text-xs mb-1">
                                                已抓取 (条)
                                            </span>
                                            <span
                                                className={cn(
                                                    "font-mono font-medium text-base",
                                                    task.status === "running"
                                                        ? "text-blue-600"
                                                        : "text-foreground"
                                                )}
                                            >
                                                {task.result_count}
                                            </span>
                                        </div>
                                        <div className="hidden sm:flex flex-col items-end">
                                            <span className="text-muted-foreground text-xs mb-1">
                                                速率
                                            </span>
                                            <span className="text-xs font-mono text-muted-foreground">
                                                {typeof task.live_metrics?.tweets_per_min_15s ===
                                                    "number"
                                                    ? `${task.live_metrics.tweets_per_min_15s}/min`
                                                    : "--"}
                                            </span>
                                        </div>
                                        <div className="hidden sm:flex flex-col items-end">
                                            <span className="text-muted-foreground text-xs mb-1">
                                                最近动作
                                            </span>
                                            <span
                                                className="text-xs text-muted-foreground max-w-36 truncate"
                                                title={String(task.latest_action?.phase ?? "--")}
                                            >
                                                {String(task.latest_action?.phase ?? "--")}
                                            </span>
                                        </div>
                                        <div className="hidden lg:flex flex-col items-end">
                                            <span className="text-muted-foreground text-xs mb-1">
                                                覆盖时间
                                            </span>
                                            <span
                                                className="text-xs text-muted-foreground max-w-40 truncate"
                                                title={rangeText(
                                                    task.time_coverage as
                                                    | Record<string, unknown>
                                                    | undefined
                                                )}
                                            >
                                                {rangeText(
                                                    task.time_coverage as
                                                    | Record<string, unknown>
                                                    | undefined
                                                )}
                                            </span>
                                        </div>
                                        <div className="hidden md:flex flex-col items-end">
                                            <span className="text-muted-foreground text-xs mb-1">
                                                创建时间
                                            </span>
                                            <span className="text-muted-foreground text-xs flex items-center gap-1">
                                                <Clock className="w-3 h-3" />
                                                {new Date(task.created_at).toLocaleDateString()}
                                            </span>
                                        </div>
                                    </div>
                                </Link>

                                <div className="p-3 bg-muted/20 border-t sm:border-t-0 sm:border-l flex items-center justify-end sm:justify-center gap-1 transition-colors">
                                    {["done", "stopped", "failed"].includes(task.status) && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="text-muted-foreground hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/20 shrink-0"
                                            disabled={resumingId === task.task_id}
                                            onClick={(e) => {
                                                e.preventDefault();
                                                handleResume(task.task_id);
                                            }}
                                            title="继续爬取"
                                        >
                                            {resumingId === task.task_id ? (
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                            ) : (
                                                <RotateCcw className="w-4 h-4" />
                                            )}
                                        </Button>
                                    )}
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-muted-foreground hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 shrink-0"
                                        onClick={(e) => {
                                            e.preventDefault();
                                            setDeleteId(task.task_id);
                                        }}
                                        title="删除任务"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </Button>
                                </div>
                            </Card>
                        );
                    })}
                </div>
            )}

            <ConfirmDialog
                open={Boolean(deleteId)}
                title="确认删除任务？"
                description="删除后任务记录将从列表移除。"
                confirmText="删除"
                cancelText="取消"
                onCancel={() => setDeleteId(null)}
                onConfirm={async () => {
                    if (!deleteId) return;
                    const id = deleteId;
                    setDeleteId(null);
                    await handleDelete(id);
                }}
            />
        </div>
    );
}
