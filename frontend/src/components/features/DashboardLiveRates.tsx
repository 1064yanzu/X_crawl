"use client";

import Link from "next/link";
import { Activity, ArrowRight, FileText, MessageSquare, Zap } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLiveRates } from "@/hooks/useAnalytics";
import { cn } from "@/lib/utils";

/* ── 脉冲指示灯 ── */
function PulseIndicator({ active }: { active: boolean }) {
    if (!active) {
        return <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/30" />;
    }
    return (
        <span className="relative inline-flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
        </span>
    );
}

/* ── 速率指标 ── */
function RateItem({
    label,
    perMin,
    perHour,
    icon: Icon,
    accentClass,
}: {
    label: string;
    perMin: number;
    perHour: number;
    icon: React.ComponentType<{ className?: string }>;
    accentClass: string;
}) {
    return (
        <div className="flex items-center gap-3 rounded-xl border border-border/50 bg-background/60 px-3.5 py-3 transition-shadow hover:shadow-sm">
            <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", accentClass)}>
                <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
                <div className="mt-0.5 flex items-baseline gap-2">
                    <span className="text-lg font-bold tabular-nums text-foreground">
                        {perMin.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                    </span>
                    <span className="text-[10px] text-muted-foreground">/分</span>
                    <span className="text-xs tabular-nums text-muted-foreground">
                        ≈ {perHour.toLocaleString(undefined, { maximumFractionDigits: 0 })}/时
                    </span>
                </div>
            </div>
        </div>
    );
}

export function DashboardLiveRates() {
    const { data, isLoading } = useLiveRates(5000);

    if (isLoading && !data) {
        return (
            <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
                <CardHeader className="pb-3">
                    <Skeleton className="h-5 w-36" />
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        <Skeleton className="h-16 rounded-xl" />
                        <Skeleton className="h-16 rounded-xl" />
                    </div>
                </CardContent>
            </Card>
        );
    }

    const rates = data;
    const isActive = (rates?.running_count ?? 0) > 0;
    const g = rates?.global_rates;

    return (
        <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
            <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-xl">
                    <Zap className={cn(
                        "h-5 w-5 transition-colors",
                        isActive ? "text-emerald-500" : "text-muted-foreground",
                    )} />
                    实时采集
                    <PulseIndicator active={isActive} />
                    {isActive && (
                        <span className="ml-auto rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                            {rates!.running_count} 运行中
                        </span>
                    )}
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
                {!isActive ? (
                    <div className="flex flex-col items-center gap-2 py-4 text-center">
                        <Activity className="h-8 w-8 text-muted-foreground/25" />
                        <p className="text-xs text-muted-foreground">暂无运行中的任务</p>
                    </div>
                ) : (
                    <>
                        <RateItem
                            label="推文采集"
                            perMin={g!.tweets_per_min_60s}
                            perHour={g!.tweets_per_hour}
                            icon={FileText}
                            accentClass="bg-primary/10 text-primary"
                        />
                        <RateItem
                            label="评论采集"
                            perMin={g!.replies_per_min_60s}
                            perHour={g!.replies_per_hour}
                            icon={MessageSquare}
                            accentClass="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                        />

                        {/* 累计数据 */}
                        <div className="flex items-center gap-4 rounded-lg bg-muted/50 px-3 py-2 text-[11px] text-muted-foreground">
                            <span>累计</span>
                            <span className="font-medium text-foreground">{g!.total_tweets.toLocaleString()} 推文</span>
                            <span className="font-medium text-foreground">{g!.total_replies.toLocaleString()} 评论</span>
                        </div>
                    </>
                )}

                <Link href="/analytics" className="block">
                    <Button variant="outline" className="w-full rounded-xl bg-background text-sm">
                        查看完整看板
                        <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                </Link>
            </CardContent>
        </Card>
    );
}
