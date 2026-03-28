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
        <div className="space-y-6">
            {/* Live rates skeleton */}
            <Skeleton className="h-[200px] w-full rounded-2xl" />
            {/* Summary cards skeleton */}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="rounded-2xl border border-border/60 bg-card/90 p-5">
                        <div className="flex items-center gap-3">
                            <Skeleton className="h-10 w-10 rounded-xl" />
                            <div className="space-y-2">
                                <Skeleton className="h-3 w-16" />
                                <Skeleton className="h-7 w-24" />
                            </div>
                        </div>
                        <Skeleton className="mt-3 h-3 w-32" />
                    </div>
                ))}
            </div>
            {/* Chart skeleton */}
            <Skeleton className="h-[400px] w-full rounded-2xl" />
            {/* Bottom row skeleton */}
            <div className="grid gap-6 xl:grid-cols-2">
                <Skeleton className="h-[320px] rounded-2xl" />
                <Skeleton className="h-[320px] rounded-2xl" />
            </div>
        </div>
    );
}

export default function AnalyticsPage() {
    const { data, isLoading } = useAnalyticsOverview();

    return (
        <div className="space-y-6 pb-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
            <PageHeader
                eyebrow="Data Insights"
                icon={BarChart3}
                title="数据看板"
                description="查看全局采集数据的趋势与分布。"
            />

            {/* 实时速率面板（独立于 overview 数据，自带轮询） */}
            <LiveRatesPanel />

            {isLoading || !data ? (
                <LoadingSkeleton />
            ) : (
                <div className="space-y-6">
                    <AnalyticsSummaryCards summary={data.summary} />
                    <DailyVolumeChart data={data.daily_volume} />
                    <div className="grid gap-6 xl:grid-cols-2">
                        <PlatformDistribution data={data.platform_distribution} />
                        <TopKeywords data={data.top_keywords} />
                    </div>
                </div>
            )}
        </div>
    );
}

