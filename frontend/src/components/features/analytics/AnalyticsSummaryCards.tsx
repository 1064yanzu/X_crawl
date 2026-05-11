"use client";
import { FileText, MessageSquare, ListChecks, RotateCcw } from "lucide-react";
import type { AnalyticsOverview } from "@/services/api";

function StatCard({
    label,
    value,
    hint,
    icon: Icon,
    accentClass,
}: {
    label: string;
    value: string | number;
    hint: string;
    icon: React.ComponentType<{ className?: string }>;
    accentClass: string;
}) {
    return (
        <div className="rounded-md border border-border bg-card p-5 shadow-sm transition-shadow hover:shadow-md">
            <div className="flex items-center gap-3">
                <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${accentClass}`}>
                    <Icon className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
                    <p className="mt-0.5 text-2xl font-bold tracking-tight text-foreground">
                        {typeof value === "number" ? value.toLocaleString() : value}
                    </p>
                </div>
            </div>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">{hint}</p>
        </div>
    );
}

export function AnalyticsSummaryCards({ summary }: { summary: AnalyticsOverview["summary"] }) {
    return (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
                label="推文总量"
                value={summary.total_tweets}
                hint={`来自 ${summary.total_tasks} 个任务`}
                icon={FileText}
                accentClass="bg-primary/10 text-primary"
            />
            <StatCard
                label="评论总量"
                value={summary.total_replies}
                hint={`${summary.active_tasks} 个任务进行中`}
                icon={MessageSquare}
                accentClass="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
            />
            <StatCard
                label="已完成任务"
                value={summary.completed_tasks}
                hint={`总计 ${summary.total_tasks} 个任务`}
                icon={ListChecks}
                accentClass="bg-blue-500/10 text-blue-600 dark:text-blue-400"
            />
            <StatCard
                label="复爬新增"
                value={summary.total_new_from_recrawl}
                hint={`${summary.recrawl_tasks} 次增量复爬`}
                icon={RotateCcw}
                accentClass="bg-amber-500/10 text-amber-600 dark:text-amber-400"
            />
        </div>
    );
}
