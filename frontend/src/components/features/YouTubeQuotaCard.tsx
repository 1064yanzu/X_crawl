"use client";

import * as React from "react";
import { Activity, Gauge, Loader2, RefreshCw, ShieldCheck, Timer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { api, type YouTubeQuotaSummary } from "@/services/api";
import { cn } from "@/lib/utils";

function formatDateTime(iso: string | null): string {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleString("zh-CN", { hour12: false });
    } catch {
        return iso;
    }
}

export function YouTubeQuotaCard() {
    const { push } = useToast();
    const [summary, setSummary] = React.useState<YouTubeQuotaSummary | null>(null);
    const [loading, setLoading] = React.useState(true);

    const refresh = React.useCallback(async () => {
        setLoading(true);
        try {
            const result = await api.youtubeApiKeys.quota();
            setSummary(result);
        } catch (error) {
            push({
                type: "error",
                title: "加载配额失败",
                description: error instanceof Error ? error.message : String(error),
            });
        } finally {
            setLoading(false);
        }
    }, [push]);

    React.useEffect(() => {
        void refresh();
        const timer = window.setInterval(refresh, 60_000);
        return () => window.clearInterval(timer);
    }, [refresh]);

    const usagePct = React.useMemo(() => {
        if (!summary || summary.total_daily_limit <= 0) return 0;
        return Math.min(100, Math.round((summary.total_used_today / summary.total_daily_limit) * 100));
    }, [summary]);

    return (
        <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
            <CardHeader className="flex flex-col gap-3 border-b border-border/50 pb-5 sm:flex-row sm:items-start sm:justify-between">
                <div>
                    <CardTitle className="flex items-center gap-2 text-xl">
                        <Gauge className="h-5 w-5 text-red-600 dark:text-red-400" /> 今日配额概览
                    </CardTitle>
                    <CardDescription className="mt-1">
                        每个 YouTube API Key 默认每日 10,000 单位；搜索 100 单位/次，list 类 1 单位/次。
                    </CardDescription>
                </div>
                <Button variant="outline" size="sm" className="rounded-xl" onClick={refresh} disabled={loading}>
                    <RefreshCw className={cn("mr-1 h-4 w-4", loading && "animate-spin")} />
                    刷新
                </Button>
            </CardHeader>
            <CardContent className="space-y-5 pt-5">
                {loading && !summary ? (
                    <div className="flex items-center justify-center gap-2 rounded-2xl border border-dashed border-border/60 bg-background/40 p-6 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在加载配额...
                    </div>
                ) : !summary || summary.total_keys === 0 ? (
                    <div className="rounded-2xl border border-dashed border-border/60 bg-background/40 p-6 text-center text-sm text-muted-foreground">
                        尚未配置任何 Key。添加 Key 后此处会出现实时配额数据。
                    </div>
                ) : (
                    <div className="space-y-5">
                        <div className="grid gap-3 sm:grid-cols-4">
                            <MetricBlock
                                icon={ShieldCheck}
                                label="可用 Key"
                                value={`${summary.active_keys} / ${summary.total_keys}`}
                                hint={
                                    summary.exhausted_keys + summary.invalid_keys > 0
                                        ? `耗尽 ${summary.exhausted_keys} · 失效 ${summary.invalid_keys}`
                                        : "全部正常"
                                }
                            />
                            <MetricBlock
                                icon={Activity}
                                label="今日用量"
                                value={summary.total_used_today.toLocaleString()}
                                hint={`上限 ${summary.total_daily_limit.toLocaleString()}`}
                            />
                            <MetricBlock
                                icon={Gauge}
                                label="剩余配额"
                                value={summary.total_remaining_today.toLocaleString()}
                                hint={`占比 ${usagePct}%`}
                            />
                            <MetricBlock
                                icon={Timer}
                                label="最近重置点"
                                value={formatDateTime(summary.earliest_reset_at)}
                                hint="按太平洋时间零点"
                                compact
                            />
                        </div>

                        <div>
                            <div className="flex items-center justify-between text-xs text-muted-foreground">
                                <span>总体消耗进度</span>
                                <span>{usagePct}%</span>
                            </div>
                            <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-muted">
                                <div
                                    className={cn(
                                        "h-full rounded-full transition-all",
                                        usagePct >= 95
                                            ? "bg-rose-500"
                                            : usagePct >= 75
                                              ? "bg-amber-500"
                                              : "bg-emerald-500",
                                    )}
                                    style={{ width: `${usagePct}%` }}
                                />
                            </div>
                            <p className="mt-2 text-xs text-muted-foreground">
                                建议保留 15% 以上缓冲，遇到配额告警时可在下方 Key 池中手动停用或添加新 Key。
                            </p>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

function MetricBlock({
    icon: Icon,
    label,
    value,
    hint,
    compact,
}: {
    icon: React.ElementType;
    label: string;
    value: string;
    hint?: string;
    compact?: boolean;
}) {
    return (
        <div className="rounded-2xl border border-border/60 bg-background/70 p-4 shadow-sm">
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                <Icon className="h-3.5 w-3.5" />
                {label}
            </div>
            <div className={cn("mt-2 font-semibold", compact ? "text-base" : "text-2xl")}>{value}</div>
            {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
        </div>
    );
}
