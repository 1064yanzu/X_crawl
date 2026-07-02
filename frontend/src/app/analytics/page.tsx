"use client";
import { BarChart3 } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalyticsOverview } from "@/hooks/useAnalytics";
import { AnalyticsSummaryCards } from "@/components/features/analytics/AnalyticsSummaryCards";
import { DailyVolumeChart } from "@/components/features/analytics/DailyVolumeChart";
import { PlatformDistribution } from "@/components/features/analytics/PlatformDistribution";
import { TopKeywords } from "@/components/features/analytics/TopKeywords";
import { LiveRatesPanel } from "@/components/features/analytics/LiveRatesPanel";

function LoadingSkeleton() {
    return (
        <div className="space-y-10">
            <Skeleton className="h-[180px] w-full" />
            <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="space-y-3">
                        <Skeleton className="h-3 w-16" />
                        <Skeleton className="h-8 w-24" />
                        <Skeleton className="h-3 w-28" />
                    </div>
                ))}
            </div>
            <Skeleton className="h-[360px] w-full" />
            <div className="grid gap-10 xl:grid-cols-2">
                <Skeleton className="h-[300px]" />
                <Skeleton className="h-[300px]" />
            </div>
        </div>
    );
}

export default function AnalyticsPage() {
    const { data, isLoading } = useAnalyticsOverview();

    return (
        <div className="space-y-14 pb-16 editorial-rise">
            <PageHeader
                eyebrow="第 01 期 · 数据台"
                icon={BarChart3}
                title="数据看板"
                description="查看全局采集数据的趋势与分布。"
            />

            <LiveRatesPanel />

            {isLoading || !data ? (
                <LoadingSkeleton />
            ) : (
                <div className="space-y-14">
                    <AnalyticsSummaryCards summary={data.summary} />
                    <div className="grid gap-10 xl:grid-cols-2">
                        <PlatformDistribution data={data.platform_distribution} />
                        <TopKeywords data={data.top_keywords} />
                    </div>
                </div>
            )}

            <section className="space-y-4">
                <div>
                    <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-[color:var(--fg-subtle)]">
                        Daily volume
                    </p>
                    <h2 className="mt-1 font-serif text-[1.5rem] font-medium leading-tight tracking-tight text-foreground">
                        采集量趋势
                    </h2>
                </div>
                <hr className="border-[var(--line)]" />
                <DailyVolumeChart />
            </section>
        </div>
    );
}
