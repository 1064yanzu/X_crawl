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

function TaskCompactRow({ task, index }: { task: TaskOut; index: number }) {
    const platformMeta = getPlatformMeta(task.platform);
    const lastUpdated = formatDateTime(getTaskLastUpdated(task));
    const phase = getTaskPhase(task);
    const queueLabel = getTaskQueueLabel(task);

    return (
        <Link
            href={`/tasks/${task.task_id}`}
            className="group relative block border-t border-[var(--line)] py-4 transition-colors duration-200 first:border-t-0 hover:bg-[var(--surface-2)]/40"
        >
            <span
                aria-hidden
                className="absolute left-0 top-4 hidden font-mono text-[9.5px] uppercase tracking-[0.2em] text-[color:var(--fg-subtle)] sm:block"
            >
                {String(index + 1).padStart(2, "0")}
            </span>
            <div className="flex items-start gap-3 sm:pl-8">
                <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                        <span className={cn("font-mono text-[10px] uppercase tracking-[0.22em]", platformMeta.badgeClass)}>
                            {platformMeta.label}
                        </span>
                        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-[color:var(--fg-subtle)]">
                            {getTaskKindLabel(task)}
                        </span>
                        {queueLabel ? (
                            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--accent)]">
                                Q {queueLabel}
                            </span>
                        ) : null}
                        <TaskStatusBadge status={task.status} riskState={task.risk_state} size="sm" />
                    </div>
                    <h4 className="line-clamp-2 font-serif text-[15px] leading-snug text-foreground">
                        {task.keyword}
                    </h4>
                    <p className="line-clamp-1 text-[12px] leading-5 text-[color:var(--fg-muted)]">{phase}</p>
                    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono text-[11px] text-[color:var(--fg-subtle)]">
                        <span className="numeric">
                            {task.source_task_id && (task.exclude_count ?? 0) > 0
                                ? `原 ${(task.exclude_count ?? 0).toLocaleString()} · 增 ${task.result_count.toLocaleString()}`
                                : `结果 ${task.result_count.toLocaleString()}`}
                        </span>
                        {task.current_page > 0 ? <span className="numeric">p.{task.current_page}</span> : null}
                        <span>{lastUpdated}</span>
                    </div>
                </div>
                <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-[color:var(--fg-subtle)] transition-all duration-200 group-hover:translate-x-0.5 group-hover:text-[var(--accent)]" />
            </div>
        </Link>
    );
}

function SectionHeading({
    icon: Icon,
    label,
    count,
    accent = "default",
}: {
    icon: React.ComponentType<{ className?: string }>;
    label: string;
    count: number;
    accent?: "default" | "primary" | "warn";
}) {
    const accentClass = {
        default: "text-[color:var(--fg-subtle)]",
        primary: "text-[var(--accent)]",
        warn: "text-[var(--warn)]",
    }[accent];
    return (
        <div className="flex items-baseline justify-between gap-3 py-2">
            <div className="flex items-center gap-2.5">
                <Icon className={cn("h-3.5 w-3.5", accentClass)} />
                <span className="font-mono text-[10.5px] uppercase tracking-[0.24em] text-[color:var(--fg-muted)]">
                    {label}
                </span>
            </div>
            <span className="font-mono numeric text-[11px] text-[color:var(--fg-subtle)]">
                {String(count).padStart(2, "0")}
            </span>
        </div>
    );
}

export function DashboardTasks() {
    const { data, isLoading } = useTasksQuery(5000);
    const tasks = (data ?? []).slice(0, 8);

    if (isLoading && tasks.length === 0) {
        return (
            <div className="space-y-3 pt-2">
                {[1, 2, 3].map((item) => (
                    <div key={item} className="space-y-2 border-t border-[var(--line)] pt-3 first:border-t-0">
                        <Skeleton className="h-3 w-24" />
                        <Skeleton className="h-4 w-2/3" />
                        <Skeleton className="h-3 w-1/2" />
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
        <div className="space-y-8 pt-2">
            {runningTasks.length > 0 ? (
                <section>
                    <SectionHeading icon={Activity} label="进行中" count={runningTasks.length} accent="primary" />
                    <div>
                        {runningTasks.slice(0, 3).map((task, idx) => (
                            <TaskCompactRow key={task.task_id} task={task} index={idx} />
                        ))}
                    </div>
                </section>
            ) : null}

            {pausedTasks.length > 0 ? (
                <section>
                    <SectionHeading icon={Pause} label="已暂停" count={pausedTasks.length} accent="warn" />
                    <div>
                        {pausedTasks.slice(0, 3).map((task, idx) => (
                            <TaskCompactRow key={task.task_id} task={task} index={idx} />
                        ))}
                    </div>
                </section>
            ) : null}

            {historyTasks.length > 0 ? (
                <section>
                    <SectionHeading icon={History} label="最近完成" count={historyTasks.length} />
                    <div>
                        {historyTasks.slice(0, 4).map((task, idx) => (
                            <TaskCompactRow key={task.task_id} task={task} index={idx} />
                        ))}
                    </div>
                </section>
            ) : null}

            <Link href="/tasks" className="inline-block">
                <Button variant="link" className="px-0">
                    查看全部队列
                    <ArrowRight className="ml-2 h-3.5 w-3.5" />
                </Button>
            </Link>
        </div>
    );
}
