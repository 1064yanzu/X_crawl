"use client";

import Link from "next/link";
import { Activity, ArrowRight, FileText, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLiveRates } from "@/hooks/useAnalytics";
import { cn } from "@/lib/utils";

function PulseIndicator({ active }: { active: boolean }) {
    if (!active) {
        return <span className="inline-block h-2 w-2 rounded-full bg-[color:var(--fg-subtle)]/40" />;
    }
    return (
        <span className="relative inline-flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--ok)] opacity-70" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--ok)]" />
        </span>
    );
}

function RateRow({
    label,
    perMin,
    perHour,
    icon: Icon,
}: {
    label: string;
    perMin: number;
    perHour: number;
    icon: React.ComponentType<{ className?: string }>;
}) {
    return (
        <div className="flex items-baseline justify-between gap-4 border-b border-dashed border-[var(--line)] py-3 last:border-b-0">
            <div className="flex items-center gap-2.5">
                <Icon className="h-3.5 w-3.5 text-[var(--accent)]" />
                <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-[color:var(--fg-muted)]">
                    {label}
                </span>
            </div>
            <div className="flex items-baseline gap-2">
                <span className="numeric font-serif text-[1.5rem] font-medium leading-none text-foreground">
                    {perMin.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--fg-subtle)]">
                    / 分
                </span>
                <span className="numeric font-mono text-[11px] text-[color:var(--fg-subtle)]">
                    ≈ {perHour.toLocaleString(undefined, { maximumFractionDigits: 0 })}/时
                </span>
            </div>
        </div>
    );
}

export function DashboardLiveRates() {
    const { data, isLoading } = useLiveRates(5000);

    if (isLoading && !data) {
        return (
            <section className="space-y-3">
                <Skeleton className="h-5 w-36" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
            </section>
        );
    }

    const rates = data;
    const isActive = (rates?.running_count ?? 0) > 0;
    const g = rates?.global_rates;

    return (
        <section aria-labelledby="live-rates-heading" className="space-y-5">
            <div className="flex items-baseline justify-between gap-3">
                <div>
                    <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-[color:var(--fg-subtle)]">
                        实时数据
                    </p>
                    <h2
                        id="live-rates-heading"
                        className="mt-1 flex items-center gap-3 font-serif text-[1.5rem] font-medium leading-tight tracking-tight text-foreground"
                    >
                        <PulseIndicator active={isActive} />
                        实时采集
                    </h2>
                </div>
                {isActive ? (
                    <p className="numeric font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--ok)]">
                        {rates!.running_count} 运行中
                    </p>
                ) : (
                    <p className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-[color:var(--fg-subtle)]">
                        Idle
                    </p>
                )}
            </div>

            <hr className="border-[var(--line)]" />

            {!isActive ? (
                <div className="flex items-center gap-3 py-4">
                    <Activity className="h-4 w-4 text-[color:var(--fg-subtle)]" />
                    <p className="text-[13px] text-[color:var(--fg-muted)]">暂无运行中的任务。</p>
                </div>
            ) : (
                <div className="space-y-0">
                    <RateRow label="推文采集" perMin={g!.tweets_per_min_60s} perHour={g!.tweets_per_hour} icon={FileText} />
                    <RateRow label="评论采集" perMin={g!.replies_per_min_60s} perHour={g!.replies_per_hour} icon={MessageSquare} />

                    <div className={cn(
 "mt-3 flex items-baseline justify-between gap-4 border-t border-[var(--line)] pt-3",
 "font-mono text-[11px] text-[color:var(--fg-subtle)]",
                    )}>
                        <span className="uppercase tracking-[0.22em]">累计</span>
                        <span className="flex items-baseline gap-4">
                            <span><span className="numeric text-foreground">{g!.total_tweets.toLocaleString()}</span> 推文</span>
                            <span><span className="numeric text-foreground">{g!.total_replies.toLocaleString()}</span> 评论</span>
                        </span>
                    </div>
                </div>
            )}

            <Link href="/analytics" className="inline-block">
                <Button variant="link" className="px-0">
                    查看完整看板
                    <ArrowRight className="ml-2 h-3.5 w-3.5" />
                </Button>
            </Link>
        </section>
    );
}
