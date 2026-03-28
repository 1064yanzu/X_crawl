"use client";
import { useMemo } from "react";
import {
    ResponsiveContainer,
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnalyticsOverview } from "@/services/api";

export function DailyVolumeChart({
    data,
}: {
    data: AnalyticsOverview["daily_volume"];
}) {
    // 取最近 30 天
    const chartData = useMemo(() => {
        const recent = data.slice(-30);
        return recent.map((d) => ({
            ...d,
            date: d.date.slice(5), // "03-25" 格式
        }));
    }, [data]);

    if (chartData.length === 0) {
        return (
            <Card className="rounded-2xl border-border/60 bg-card/90 shadow-sm backdrop-blur-sm">
                <CardHeader className="pb-3">
                    <CardTitle className="text-lg">每日采集趋势</CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="py-12 text-center text-sm text-muted-foreground">暂无数据</p>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="rounded-2xl border-border/60 bg-card/90 shadow-sm backdrop-blur-sm">
            <CardHeader className="pb-3">
                <CardTitle className="text-lg">每日采集趋势</CardTitle>
                <p className="text-xs text-muted-foreground">最近 30 天推文与评论采集量</p>
            </CardHeader>
            <CardContent>
                <div className="h-[320px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                            <defs>
                                <linearGradient id="gradTweets" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="gradReplies" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="hsl(152, 57%, 48%)" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="hsl(152, 57%, 48%)" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" strokeOpacity={0.5} />
                            <XAxis
                                dataKey="date"
                                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                                axisLine={false}
                                tickLine={false}
                            />
                            <YAxis
                                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                                axisLine={false}
                                tickLine={false}
                            />
                            <Tooltip
                                contentStyle={{
                                    borderRadius: "12px",
                                    border: "1px solid hsl(var(--border))",
                                    background: "hsl(var(--card))",
                                    boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                                    fontSize: 12,
                                }}
                            />
                            <Legend
                                iconType="circle"
                                wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                            />
                            <Area
                                type="monotone"
                                dataKey="tweets"
                                name="推文"
                                stroke="hsl(var(--primary))"
                                fill="url(#gradTweets)"
                                strokeWidth={2}
                            />
                            <Area
                                type="monotone"
                                dataKey="replies"
                                name="评论"
                                stroke="hsl(152, 57%, 48%)"
                                fill="url(#gradReplies)"
                                strokeWidth={2}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </CardContent>
        </Card>
    );
}
