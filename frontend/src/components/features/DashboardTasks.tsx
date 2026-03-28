"use client";
import Link from "next/link";
import { Activity, ArrowRight, Database, History, Pause } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useTasksQuery } from "@/hooks/useTasks";
import { getPlatformMeta } from "@/lib/platformRegistry";
import { formatDateTime, getTaskKindLabel, getTaskLastUpdated, getTaskPhase, getTaskQueueLabel, isTaskActive } from "@/lib/task-ui";
import type { TaskOut } from "@/services/api";
import { TaskStatusBadge } from "@/components/features/task-detail/TaskStatusBadge";
import { cn } from "@/lib/utils";

function TaskCompactCard({ task }: { task: TaskOut }) {
    const platformMeta = getPlatformMeta(task.platform);
    const lastUpdated = formatDateTime(getTaskLastUpdated(task));
    const phase = getTaskPhase(task);
    const queueLabel = getTaskQueueLabel(task);

    return (
        <Link
            href={`/tasks/${task.task_id}`}
            className="group block rounded-2xl border border-border/60 bg-background/75 p-4 transition-all duration-200 hover:border-primary/25 hover:bg-background hover:shadow-sm"
        >
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                        <span className={cn("inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium", platformMeta.badgeClass)}>
                            {platformMeta.label}
                        </span>
                        <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                            {getTaskKindLabel(task)}
                        </span>
                        {queueLabel ? <span className="rounded-full bg-primary/8 px-2 py-0.5 text-[11px] font-medium text-primary">队列 {queueLabel}</span> : null}
                        <TaskStatusBadge status={task.status} riskState={task.risk_state} size="sm" />
                    </div>
                    <h4 className="line-clamp-2 text-sm font-semibold text-foreground">{task.keyword}</h4>
                    <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">{phase}</p>
                </div>
                <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-foreground" />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
                <span>
                    {task.source_task_id && (task.exclude_count ?? 0) > 0
                        ? `原始 ${(task.exclude_count ?? 0).toLocaleString()} · 新增 ${task.result_count.toLocaleString()}`
                        : `结果 ${task.result_count.toLocaleString()}`}
                </span>
                {task.current_page > 0 ? <span>页数 {task.current_page}</span> : null}
                <span>更新 {lastUpdated}</span>
            </div>
        </Link>
    );
}

export function DashboardTasks() {
    const { data, isLoading } = useTasksQuery(5000);
    const tasks = (data ?? []).slice(0, 8);

    if (isLoading && tasks.length === 0) {
        return (
            <div className="space-y-3">
                {[1, 2, 3].map((item) => (
                    <div key={item} className="rounded-2xl border border-border/60 bg-card/80 p-4 shadow-sm">
                        <Skeleton className="h-5 w-24" />
                        <Skeleton className="mt-3 h-4 w-2/3" />
                        <Skeleton className="mt-3 h-4 w-1/2" />
                    </div>
                ))}
            </div>
        );
    }

    if (tasks.length === 0) {
        return (
            <EmptyState
                icon={Database}
                title="当前还没有历史任务"
                description="创建第一个采集任务后，这里会持续更新进行中队列和最近完成记录。"
            />
        );
    }

    const runningTasks = tasks.filter((task) => task.status === "running" || task.status === "pending");
    const pausedTasks = tasks.filter((task) => task.status === "paused");
    const historyTasks = tasks.filter((task) => !isTaskActive(task.status));

    return (
        <div className="space-y-6">
            {runningTasks.length > 0 ? (
                <section className="space-y-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <Activity className="h-4 w-4 text-primary" />
                        进行中任务
                        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{runningTasks.length}</span>
                    </div>
                    <div className="space-y-3">
                        {runningTasks.slice(0, 3).map((task) => (
                            <TaskCompactCard key={task.task_id} task={task} />
                        ))}
                    </div>
                </section>
            ) : null}

            {pausedTasks.length > 0 ? (
                <section className="space-y-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <Pause className="h-4 w-4 text-amber-500" />
                        已暂停任务
                        <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-600 dark:text-amber-400">{pausedTasks.length}</span>
                    </div>
                    <div className="space-y-3">
                        {pausedTasks.slice(0, 3).map((task) => (
                            <TaskCompactCard key={task.task_id} task={task} />
                        ))}
                    </div>
                </section>
            ) : null}

            {historyTasks.length > 0 ? (
                <section className="space-y-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                        <History className="h-4 w-4 text-muted-foreground" />
                        最近完成
                        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{historyTasks.length}</span>
                    </div>
                    <div className="space-y-3">
                        {historyTasks.slice(0, 4).map((task) => (
                            <TaskCompactCard key={task.task_id} task={task} />
                        ))}
                    </div>
                </section>
            ) : null}

            <Link href="/tasks" className="block">
                <Button variant="outline" className="w-full rounded-xl bg-background">
                    查看全部队列
                    <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
            </Link>
        </div>
    );
}
