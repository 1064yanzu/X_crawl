"use client";
import {
    ResponsiveContainer,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    Cell,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnalyticsOverview } from "@/services/api";

const PLATFORM_LABELS: Record<string, string> = {
    x: "X (Twitter)",
    weibo: "微博",
};

const PLATFORM_COLORS: Record<string, string> = {
    x: "hsl(var(--primary))",
    weibo: "hsl(25, 95%, 53%)",
};

export function PlatformDistribution({
    data,
}: {
    data: AnalyticsOverview["platform_distribution"];
}) {
    const chartData = data.map((d) => ({
        ...d,
        label: PLATFORM_LABELS[d.platform] ?? d.platform,
    }));

    if (chartData.length === 0) {
        return (
            <Card className="rounded-md border-border bg-card shadow-sm ">
                <CardHeader className="pb-3">
                    <CardTitle className="text-lg">平台分布</CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="py-12 text-center text-sm text-muted-foreground">暂无数据</p>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="rounded-md border-border bg-card shadow-sm ">
            <CardHeader className="pb-3">
                <CardTitle className="text-lg">平台分布</CardTitle>
                <p className="text-xs text-muted-foreground">各平台推文与评论采集量</p>
            </CardHeader>
            <CardContent>
                <div className="h-[260px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" strokeOpacity={0.5} />
                            <XAxis
                                dataKey="label"
                                tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
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
                            <Legend iconType="circle" wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                            <Bar dataKey="tweets" name="推文" radius={[6, 6, 0, 0]}>
                                {chartData.map((entry) => (
                                    <Cell
                                        key={entry.platform}
                                        fill={PLATFORM_COLORS[entry.platform] ?? "hsl(var(--primary))"}
                                    />
                                ))}
                            </Bar>
                            <Bar dataKey="replies" name="评论" radius={[6, 6, 0, 0]}>
                                {chartData.map((entry) => (
                                    <Cell
                                        key={entry.platform}
                                        fill={PLATFORM_COLORS[entry.platform] ?? "hsl(152, 57%, 48%)"}
                                        opacity={0.6}
                                    />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </CardContent>
        </Card>
    );
}
