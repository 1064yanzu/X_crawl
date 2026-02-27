"use client";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, Database, Search, ArrowRight, History, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTasksQuery } from "@/hooks/useTasks";

function coverageText(task: { time_coverage?: Record<string, unknown> }) {
    const c = task.time_coverage ?? {};
    const start = typeof c.combined_start_at === "string" ? c.combined_start_at : "";
    const end = typeof c.combined_end_at === "string" ? c.combined_end_at : "";
    if (!start || !end) return "覆盖时间 --";
    return `覆盖 ${new Date(start).toLocaleDateString()} ~ ${new Date(end).toLocaleDateString()}`;
}

export function DashboardTasks() {
    const { data, isLoading } = useTasksQuery(5000);
    const tasks = (data ?? []).slice(0, 4);
    const loading = isLoading;

    if (loading && tasks.length === 0) {
        return (
            <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                    <div key={i} className="h-20 bg-card rounded-xl border animate-pulse" />
                ))}
            </div>
        );
    }

    if (tasks.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-10 text-center border-dashed rounded-2xl bg-muted/20 border">
                <Database className="w-8 h-8 text-muted-foreground/30 mb-3" />
                <p className="text-sm text-muted-foreground font-medium">当前暂无历史调度记录</p>
                <p className="text-xs text-muted-foreground mb-4">创建您的第一个抓取任务</p>
            </div>
        );
    }

    const activeTasks = tasks.filter(t => t.status === "running" || t.status === "pending");
    const historyTasks = tasks.filter(t => t.status !== "running" && t.status !== "pending");

    return (
        <div className="space-y-6">
            {/* 1. Real-time active data (实时爬取的数据/运行状态) */}
            {activeTasks.length > 0 && (
                <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
                        <Activity className="w-4 h-4 text-blue-500" />
                        正在运行的采集流 (Real-time Operations)
                    </h3>
                    <div className="grid gap-3">
                        {activeTasks.map(task => (
                            <Link key={task.task_id} href={`/tasks/${task.task_id}`}>
                                <Card className="p-4 hover:border-primary/50 transition-all duration-300 shadow-sm flex items-center justify-between group overflow-hidden relative">
                                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500 animate-pulse" />
                                    <div className="flex items-center gap-3">
                                        <div className="bg-blue-500/10 text-blue-600 p-2 rounded-lg">
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-foreground text-sm flex items-center gap-1.5">
                                                <Search className="w-3.5 h-3.5 text-muted-foreground" />
                                                {task.keyword}
                                            </h4>
                                            <p className="text-xs text-muted-foreground mt-0.5 tracking-tight flex items-center gap-2">
                                                <span className="font-mono">ID: {task.task_id.substring(0, 6)}</span>
                                                <span className="text-blue-500 font-medium ml-1">已抓取 {task.result_count} 条实时数据</span>
                                            </p>
                                            <p className="text-[11px] text-muted-foreground mt-1 font-mono">
                                                {typeof task.live_metrics?.tweets_per_min_15s === "number"
                                                    ? `速率 ${task.live_metrics.tweets_per_min_15s}/min`
                                                    : "速率 --"}
                                                {task.status === "pending" && task.queue_position
                                                    ? ` · 队列#${task.queue_position}`
                                                    : ""}
                                            </p>
                                            <p className="text-[11px] text-muted-foreground mt-1">
                                                {coverageText(task)}
                                                {typeof task.live_metrics?.host_mem_used_percent === "number"
                                                    ? ` · 内存 ${task.live_metrics.host_mem_used_percent}%`
                                                    : ""}
                                            </p>
                                            {task.risk_state !== "none" && (
                                                <Badge variant="outline" className="mt-1 h-5 border-amber-300 text-amber-600">
                                                    风险: {task.risk_state}
                                                </Badge>
                                            )}
                                        </div>
                                    </div>
                                    <Button variant="ghost" size="icon" className="group-hover:translate-x-1 transition-transform">
                                        <ArrowRight className="w-4 h-4 text-muted-foreground" />
                                    </Button>
                                </Card>
                            </Link>
                        ))}
                    </div>
                </div>
            )}

            {/* 2. Historical operations (用户的历史操作) */}
            {historyTasks.length > 0 && (
                <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-muted-foreground flex items-center gap-2 mt-2">
                        <History className="w-4 h-4" />
                        最近完成记录 (Historical Data)
                    </h3>
                    <div className="grid gap-3">
                        {historyTasks.map(task => (
                            <Link key={task.task_id} href={`/tasks/${task.task_id}`}>
                                <Card className="p-3 hover:bg-muted/50 transition-all duration-300 shadow-none border flex items-center justify-between group">
                                    <div className="flex items-center gap-3">
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <h4 className="font-medium text-foreground text-sm">{task.keyword}</h4>
                                                <Badge variant="outline" className={cn(
                                                    "text-[10px] px-1.5 py-0 h-4 border-0",
                                                    task.status === "done" ? "bg-green-500/10 text-green-600" : "bg-red-500/10 text-red-600"
                                                )}>
                                                    {task.status === "done" ? "成功" : "失败/终止"}
                                                </Badge>
                                            </div>
                                            <p className="text-xs text-muted-foreground mt-0.5 font-mono">
                                                收集量: {task.result_count} | {new Date(task.created_at).toLocaleString()}
                                            </p>
                                        </div>
                                    </div>
                                    <ArrowRight className="w-4 h-4 text-muted-foreground/40 group-hover:text-foreground transition-colors" />
                                </Card>
                            </Link>
                        ))}
                    </div>
                </div>
            )}

            <div className="pt-2">
                <Link href="/tasks" className="block">
                    <Button variant="outline" className="w-full text-muted-foreground bg-muted/20">
                        查看全部历史队列 <ArrowRight className="w-3.5 h-3.5 ml-2" />
                    </Button>
                </Link>
            </div>
        </div>
    );
}
