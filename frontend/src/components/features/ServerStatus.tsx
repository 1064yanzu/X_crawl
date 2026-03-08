"use client";
import * as React from "react";
import { ActivitySquare, AppWindow, CheckCircle2, CircleAlert, PlugZap, TerminalSquare } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useHealthQuery } from "@/hooks/useHealth";
import { API_BASE_URL, HealthResponse } from "@/services/api";
import { StatCard } from "@/components/ui/stat-card";

export function ServerStatus() {
    const { data: health, isLoading, isError, error: queryError } = useHealthQuery();
    const [fallbackHealth, setFallbackHealth] = React.useState<HealthResponse | null>(null);
    const [fallbackError, setFallbackError] = React.useState<string>("");
    const [lastCheckAt, setLastCheckAt] = React.useState<string>("");

    React.useEffect(() => {
        const toMessage = (value: unknown) => {
            if (value instanceof Error) return value.message;
            return String(value ?? "fallback failed");
        };

        const run = async () => {
            try {
                const resp = await fetch(`${API_BASE_URL}/health?t=${Date.now()}`, { cache: "no-store" });
                setLastCheckAt(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
                if (!resp.ok) {
                    setFallbackError(`HTTP ${resp.status}`);
                    return;
                }
                const data = await resp.json() as HealthResponse;
                setFallbackHealth(data);
                setFallbackError("");
            } catch (e: unknown) {
                setFallbackError(toMessage(e));
            }
        };

        if (isError) run();
        const timer = setInterval(run, 10000);
        return () => clearInterval(timer);
    }, [isError]);

    if (isLoading) {
        return (
            <div className="space-y-3 rounded-[1.5rem] border border-border/60 bg-card/90 p-5 shadow-sm">
                <Skeleton className="h-6 w-32" />
                <div className="grid gap-3 sm:grid-cols-2">
                    <Skeleton className="h-24 w-full" />
                    <Skeleton className="h-24 w-full" />
                </div>
            </div>
        );
    }

    const effectiveHealth = fallbackHealth ?? health;
    const isOnline = Boolean(effectiveHealth && effectiveHealth.status === "healthy");
    const browserConnected = Boolean(effectiveHealth?.browser_detected);
    const envReady = Boolean(effectiveHealth?.user_data_detected);

    return (
        <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
            <CardHeader className="pb-4">
                <div className="flex items-center justify-between gap-3">
                    <div>
                        <CardTitle className="flex items-center gap-2 text-xl">
                            <ActivitySquare className="h-5 w-5 text-primary" />
                            系统状态
                        </CardTitle>
                        <CardDescription className="mt-1">
                            默认展示用户真正关心的可用性状态，技术排查信息收纳到下方。
                        </CardDescription>
                    </div>
                    {isLoading ? (
                        <Badge variant="secondary">检查中</Badge>
                    ) : isOnline ? (
                        <Badge variant="success">服务在线</Badge>
                    ) : (
                        <Badge variant="destructive">服务异常</Badge>
                    )}
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                    <StatCard
                        label="后端服务"
                        value={isOnline ? "可用" : "不可用"}
                        hint={lastCheckAt ? `最近检查 ${lastCheckAt}` : "等待首次检查"}
                        icon={isOnline ? CheckCircle2 : CircleAlert}
                        tone={isOnline ? "success" : "warning"}
                    />
                    <StatCard
                        label="浏览器环境"
                        value={browserConnected ? "已连接" : "未连接"}
                        hint={envReady ? "本地配置已就绪" : "用户数据目录未就绪"}
                        icon={browserConnected ? PlugZap : AppWindow}
                        tone={browserConnected ? "primary" : "default"}
                    />
                </div>

                <div className="grid gap-3 rounded-2xl border border-border/60 bg-muted/20 p-4 sm:grid-cols-3">
                    <StatusLine
                        label="平台"
                        value={effectiveHealth?.platform ? effectiveHealth.platform.toUpperCase() : "--"}
                    />
                    <StatusLine
                        label="运行模式"
                        value={browserConnected ? "浏览器已接入" : "等待浏览器启动"}
                    />
                    <StatusLine
                        label="当前建议"
                        value={isOnline ? (browserConnected ? "可直接发起采集" : "先配置浏览器") : "先检查服务"}
                    />
                </div>

                <details className="group rounded-2xl border border-border/60 bg-background/70 p-4">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-foreground">
                        <span className="flex items-center gap-2">
                            <TerminalSquare className="h-4 w-4 text-muted-foreground" />
                            技术详情
                        </span>
                        <span className="text-xs text-muted-foreground group-open:hidden">展开排查信息</span>
                        <span className="hidden text-xs text-muted-foreground group-open:inline">收起</span>
                    </summary>
                    <div className="mt-3 space-y-2 border-t border-border/60 pt-3 text-xs text-muted-foreground">
                        <div>API 地址：<span className="font-mono text-foreground">{API_BASE_URL}</span></div>
                        <div>React Query：{isError ? `error${queryError instanceof Error ? ` | ${queryError.message}` : ""}` : "ok"}</div>
                        <div>Fallback 探测：{fallbackError ? `error | ${fallbackError}` : fallbackHealth ? "ok" : "idle"}</div>
                        <div>最近检查：{lastCheckAt || "--"}</div>
                    </div>
                </details>
            </CardContent>
        </Card>
    );
}

function StatusLine({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-xl border border-border/60 bg-card/80 px-3 py-3 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
            <p className="mt-1 text-sm font-medium text-foreground">{value}</p>
        </div>
    );
}
