"use client";

import Link from "next/link";
import { Activity, ArrowUpRight, Clock, FileText, MessageSquare, Zap } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useLiveRates } from "@/hooks/useAnalytics";
import { getPlatformMeta } from "@/lib/platformRegistry";
import type { TaskRateItem } from "@/services/api";
import { cn } from "@/lib/utils";

/* ── 时间格式工具 ── */
function formatElapsed(sec: number): string {
    if (sec < 60) return `${sec}s`;
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    if (m < 60) return `${m}m ${s}s`;
    const h = Math.floor(m / 60);
    const rm = m % 60;
    return `${h}h ${rm}m`;
}

/* ── 速率数字动画 ── */
function RateValue({ value, unit, size = "lg" }: { value: number; unit: string; size?: "lg" | "sm" }) {
    const isActive = value > 0;
    return (
        <span className={cn(
            "tabular-nums font-bold tracking-tight transition-colors duration-500",
            size === "lg" ? "text-3xl" : "text-xl",
            isActive ? "text-foreground" : "text-muted-foreground/60",
        )}>
            {value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
            <span className={cn(
                "ml-1 font-medium",
                size === "lg" ? "text-sm" : "text-xs",
                "text-muted-foreground",
            )}>
                {unit}
            </span>
        </span>
    );
}

/* ── 脉冲指示灯 ── */
function PulseIndicator({ active }: { active: boolean }) {
    if (!active) {
        return <span className="inline-block h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />;
    }
    return (
        <span className="relative inline-flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
        </span>
    );
}

/* ── 单任务速率行 ── */
function TaskRateRow({ item }: { item: TaskRateItem }) {
    const platform = getPlatformMeta(item.platform);
    // idle_sec < 30 说明任务近期有活动事件（翻页、解析等），脉冲灯保持绿色
    const isActive = (item.idle_sec ?? 999) < 30 || item.tweets_per_min_60s > 0 || item.replies_per_min_60s > 0;

    return (
        <Link
            href={`/tasks/${item.task_id}`}
            className="group block rounded-xl border border-border/50 bg-background/60 p-3.5 transition-all duration-200 hover:border-primary/20 hover:bg-background hover:shadow-sm"
        >
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                        <PulseIndicator active={isActive} />
                        <span className={cn("inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium", platform.badgeClass)}>
                            {platform.label}
                        </span>
                        <span className="truncate text-sm font-semibold text-foreground">{item.keyword}</span>
                    </div>
                    <p className="mt-1.5 line-clamp-1 text-xs text-muted-foreground">{item.crawl_phase}</p>
                </div>
                <ArrowUpRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/50 transition-all group-hover:text-primary" />
            </div>

            {/* 速率指标栅格 */}
            <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
                <RateMetric
                    label="推文/分"
                    value15s={item.tweets_per_min_15s}
                    value60s={item.tweets_per_min_60s}
                />
                <RateMetric
                    label="评论/分"
                    value15s={item.replies_per_min_15s}
                    value60s={item.replies_per_min_60s}
                />
                <div>
                    <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">推文/时</p>
                    <p className="mt-0.5 text-sm font-bold tabular-nums text-foreground">
                        {item.tweets_per_hour.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </p>
                </div>
                <div>
                    <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">评论/时</p>
                    <p className="mt-0.5 text-sm font-bold tabular-nums text-foreground">
                        {item.replies_per_hour.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </p>
                </div>
            </div>

            {/* 底部统计 */}
            <div className="mt-2.5 flex items-center gap-4 text-[11px] text-muted-foreground">
                <span className="flex items-center gap-1">
                    <FileText className="h-3 w-3" />
                    {item.result_count.toLocaleString()} 推文
                </span>
                <span className="flex items-center gap-1">
                    <MessageSquare className="h-3 w-3" />
                    {item.replies_fetched.toLocaleString()} 评论
                </span>
                <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatElapsed(item.elapsed_sec)}
                </span>
            </div>
        </Link>
    );
}

/* ── 速率指标（带 15s/60s 对比） ── */
function RateMetric({ label, value15s, value60s }: { label: string; value15s: number; value60s: number }) {
    return (
        <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
            <div className="mt-0.5 flex items-baseline gap-1.5">
                <span className="text-sm font-bold tabular-nums text-foreground">
                    {value60s.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                </span>
                <span className={cn(
                    "text-[10px] tabular-nums",
                    value15s > value60s
                        ? "text-emerald-600 dark:text-emerald-400"
                        : value15s < value60s * 0.5
                            ? "text-amber-600 dark:text-amber-400"
                            : "text-muted-foreground",
                )}>
                    {value15s > value60s ? "↑" : value15s < value60s * 0.5 ? "↓" : "~"}
                    {value15s.toFixed(1)}
                </span>
            </div>
        </div>
    );
}

/* ── 主面板 ── */
export function LiveRatesPanel() {
    const { data, isLoading } = useLiveRates(5000);

    if (isLoading && !data) {
        return (
            <Card className="rounded-2xl border-border/60 bg-card/90 shadow-sm backdrop-blur-sm">
                <CardHeader className="pb-3">
                    <Skeleton className="h-5 w-40" />
                </CardHeader>
                <CardContent>
                    <div className="space-y-4">
                        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                            {[1, 2, 3, 4].map((i) => (
                                <Skeleton key={i} className="h-20 rounded-xl" />
                            ))}
                        </div>
                        <Skeleton className="h-24 rounded-xl" />
                    </div>
                </CardContent>
            </Card>
        );
    }

    const rates = data;
    const isActive = (rates?.running_count ?? 0) > 0;
    const g = rates?.global_rates;

    return (
        <Card className="rounded-2xl border-border/60 bg-card/90 shadow-sm backdrop-blur-sm">
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2.5 text-lg">
                        <div className={cn(
                            "flex h-8 w-8 items-center justify-center rounded-lg transition-colors",
                            isActive
                                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                : "bg-muted text-muted-foreground",
                        )}>
                            <Zap className="h-4 w-4" />
                        </div>
                        实时采集速率
                        <PulseIndicator active={isActive} />
                    </CardTitle>
                    {isActive && (
                        <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                            {rates!.running_count} 个任务运行中
                        </span>
                    )}
                </div>
                <p className="text-xs text-muted-foreground">
                    {isActive ? "数据每 5 秒自动刷新；左侧主值基于最近 60 秒，右侧箭头值基于最近 15 秒，并非累计结果数" : "当前没有正在运行的任务"}
                </p>
            </CardHeader>
            <CardContent>
                {!isActive ? (
                    <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
                        <Activity className="h-10 w-10 text-muted-foreground/30" />
                        <p className="text-sm text-muted-foreground">
                            开始一个采集任务后，这里将实时展示采集速率
                        </p>
                    </div>
                ) : (
                    <div className="space-y-5">
                        {/* 全局速率卡片 */}
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                            <GlobalRateCard
                                label="推文 / 分钟"
                                value={g!.tweets_per_min_60s}
                                instantValue={g!.tweets_per_min_15s}
                                accentClass="bg-primary/10 text-primary"
                                icon={FileText}
                            />
                            <GlobalRateCard
                                label="评论 / 分钟"
                                value={g!.replies_per_min_60s}
                                instantValue={g!.replies_per_min_15s}
                                accentClass="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                icon={MessageSquare}
                            />
                            <GlobalRateCard
                                label="推文 / 小时"
                                value={g!.tweets_per_hour}
                                instantValue={null}
                                accentClass="bg-blue-500/10 text-blue-600 dark:text-blue-400"
                                icon={FileText}
                            />
                            <GlobalRateCard
                                label="评论 / 小时"
                                value={g!.replies_per_hour}
                                instantValue={null}
                                accentClass="bg-amber-500/10 text-amber-600 dark:text-amber-400"
                                icon={MessageSquare}
                            />
                        </div>

                        {/* 累计统计 */}
                        <div className="flex items-center gap-6 rounded-xl bg-muted/50 px-4 py-2.5 text-xs text-muted-foreground">
                            <span>运行中任务累计：</span>
                            <span className="font-semibold text-foreground">{g!.total_tweets.toLocaleString()} 推文</span>
                            <span className="font-semibold text-foreground">{g!.total_replies.toLocaleString()} 评论</span>
                        </div>

                        {/* 每任务明细 */}
                        <div className="space-y-2.5">
                            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                                各任务速率明细
                            </p>
                            {rates!.task_rates.map((item) => (
                                <TaskRateRow key={item.task_id} item={item} />
                            ))}
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

/* ── 全局速率卡片 ── */
function GlobalRateCard({
    label,
    value,
    instantValue,
    accentClass,
    icon: Icon,
}: {
    label: string;
    value: number;
    instantValue: number | null;
    accentClass: string;
    icon: React.ComponentType<{ className?: string }>;
}) {
    return (
        <div className="rounded-xl border border-border/50 bg-background/60 p-4 transition-shadow hover:shadow-sm">
            <div className="flex items-center gap-2.5">
                <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg", accentClass)}>
                    <Icon className="h-4 w-4" />
                </div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
            </div>
            <div className="mt-2.5 flex items-baseline gap-2">
                <RateValue value={value} unit="" size="sm" />
                {instantValue !== null && (
                    <span className={cn(
                        "text-[10px] tabular-nums",
                        instantValue > value
                            ? "text-emerald-600 dark:text-emerald-400"
                            : instantValue < value * 0.5
                                ? "text-amber-600 dark:text-amber-400"
                                : "text-muted-foreground",
                    )}>
                        实时 {instantValue.toFixed(1)}
                    </span>
                )}
            </div>
        </div>
    );
}
