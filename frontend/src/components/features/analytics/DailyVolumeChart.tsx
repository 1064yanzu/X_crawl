"use client";
import * as React from "react";
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend,
} from "recharts";
import { api, type CrawlVolumeResponse } from "@/services/api";

/* ── 时间格式化工具 ── */
function fmtBucket(bucket: string): string {
    // bucket 格式: "YYYY-MM-DDTHH:MM"
    if (!bucket || bucket.length < 16) return bucket;
    const datePart = bucket.slice(5, 10);  // "MM-DD"
    const timePart = bucket.slice(11, 16); // "HH:MM"
    return `${datePart} ${timePart}`;
}

/** 只显示整点，避免 X 轴刻度密集 */
function shouldShowTick(bucket: string, totalCount: number): boolean {
    if (!bucket || bucket.length < 16) return false;
    const minute = bucket.slice(14, 16); // "00" | "10" | ...
    // 数据点 ≤ 72 时显示每整小时（:00）；更多时每 2 小时
    if (totalCount <= 72) return minute === "00";
    if (totalCount <= 144) return minute === "00" && parseInt(bucket.slice(11, 13)) % 2 === 0;
    return minute === "00" && parseInt(bucket.slice(11, 13)) % 4 === 0;
}

/* ── 自定义 Tooltip ── */
const CustomTooltip = ({ active, payload, label }: {
    active?: boolean;
    payload?: Array<{ name: string; value: number; color: string }>;
    label?: string;
}) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="rounded-xl border border-border/60 bg-card/95 backdrop-blur-sm px-3 py-2 shadow-lg text-xs">
            <p className="font-semibold text-foreground mb-1">{label}</p>
            {payload.map((p) => (
                <div key={p.name} className="flex items-center gap-2 text-muted-foreground">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} />
                    <span>{p.name}：<span className="font-medium text-foreground">{p.value.toLocaleString()}</span></span>
                </div>
            ))}
        </div>
    );
};

/* ── 时间范围选项 ── */
const RANGE_OPTIONS = [
    { label: "6h", hours: 6 },
    { label: "24h", hours: 24 },
    { label: "48h", hours: 48 },
    { label: "7d", hours: 168 },
];

/* ── 主组件 ── */
export function DailyVolumeChart() {
    const [hoursBack, setHoursBack] = React.useState(24);
    const [data, setData] = React.useState<CrawlVolumeResponse | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState<string | null>(null);

    React.useEffect(() => {
        let cancelled = false;
        setLoading(true);
        api.analytics.crawlVolume(hoursBack)
            .then((res) => {
                if (!cancelled) {
                    setData(res);
                    setError(null);
                }
            })
            .catch((e) => {
                if (!cancelled) setError(String(e));
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => { cancelled = true; };
    }, [hoursBack]);

    const chartData = React.useMemo(() => {
        if (!data?.buckets?.length) return [];
        return data.buckets.map((b) => ({
            bucket: b.bucket,
            label: fmtBucket(b.bucket),
            tweets: b.tweets,
            replies: b.replies,
            total: b.tweets + b.replies,
        }));
    }, [data]);

    const totalBuckets = chartData.length;

    return (
        <div className="flex flex-col gap-3">
            {/* 头部：时间范围切换 */}
            <div className="flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                    <p className="text-xs font-medium text-muted-foreground">
                        采集量趋势 <span className="text-primary">· 10 分钟粒度</span>
                    </p>
                    {data && (
                        <p className="text-[10px] text-muted-foreground/60">
                            共 {(data.total_tweets + data.total_replies).toLocaleString()} 条 ·
                            推文 {data.total_tweets.toLocaleString()} ·
                            评论 {data.total_replies.toLocaleString()}
                        </p>
                    )}
                </div>
                <div className="flex gap-1 rounded-lg bg-muted/30 p-0.5">
                    {RANGE_OPTIONS.map((opt) => (
                        <button
                            key={opt.hours}
                            onClick={() => setHoursBack(opt.hours)}
                            className={`rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors ${
                                hoursBack === opt.hours
                                    ? "bg-primary text-primary-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            }`}
                        >
                            {opt.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* 图表区域 */}
            {loading ? (
                <div className="flex h-[180px] items-center justify-center">
                    <div className="flex gap-1.5">
                        {[0, 1, 2].map((i) => (
                            <span
                                key={i}
                                className="h-1.5 w-1.5 rounded-full bg-primary/60 animate-bounce"
                                style={{ animationDelay: `${i * 150}ms` }}
                            />
                        ))}
                    </div>
                </div>
            ) : error ? (
                <div className="flex h-[180px] items-center justify-center text-xs text-destructive/70">
                    数据加载失败
                </div>
            ) : chartData.length === 0 ? (
                <div className="flex h-[180px] items-center justify-center text-xs text-muted-foreground/60">
                    暂无采集记录
                </div>
            ) : (
                <ResponsiveContainer width="100%" height={180}>
                    <AreaChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                        <defs>
                            <linearGradient id="gradTweets" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
                                <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0.02} />
                            </linearGradient>
                            <linearGradient id="gradReplies" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.3} />
                                <stop offset="95%" stopColor="#a78bfa" stopOpacity={0.02} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border)/0.4)" vertical={false} />
                        <XAxis
                            dataKey="label"
                            tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
                            tickLine={false}
                            axisLine={false}
                            interval="preserveStartEnd"
                            tickFormatter={(v, i) => {
                                const b = chartData[i]?.bucket ?? "";
                                return shouldShowTick(b, totalBuckets) ? v.slice(6) : "";
                            }}
                        />
                        <YAxis
                            tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
                            tickLine={false}
                            axisLine={false}
                            tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)}
                        />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend
                            iconSize={8}
                            wrapperStyle={{ fontSize: 10, paddingTop: 4 }}
                            formatter={(value) => value === "tweets" ? "推文" : "评论"}
                        />
                        <Area
                            type="monotone"
                            dataKey="tweets"
                            name="tweets"
                            stroke="hsl(var(--primary))"
                            strokeWidth={1.5}
                            fill="url(#gradTweets)"
                            dot={false}
                            activeDot={{ r: 3, strokeWidth: 0 }}
                        />
                        <Area
                            type="monotone"
                            dataKey="replies"
                            name="replies"
                            stroke="#a78bfa"
                            strokeWidth={1.5}
                            fill="url(#gradReplies)"
                            dot={false}
                            activeDot={{ r: 3, strokeWidth: 0 }}
                        />
                    </AreaChart>
                </ResponsiveContainer>
            )}
        </div>
    );
}
