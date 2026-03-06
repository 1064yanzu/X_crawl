"use client";
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { AppWindow, ActivitySquare } from "lucide-react";
import { useHealthQuery } from "@/hooks/useHealth";
import { API_BASE_URL, HealthResponse } from "@/services/api";

export function ServerStatus() {
    const { data: health, isLoading: loading, isError: error, error: queryError } = useHealthQuery();
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
                setLastCheckAt(new Date().toLocaleTimeString());
                if (!resp.ok) {
                    setFallbackError(`fallback http ${resp.status}`);
                    return;
                }
                const data = await resp.json() as HealthResponse;
                setFallbackHealth(data);
                setFallbackError("");
            } catch (e: unknown) {
                setFallbackError(toMessage(e));
            }
        };

        if (error) run();
        const timer = setInterval(run, 10000);
        return () => clearInterval(timer);
    }, [error]);

    if (loading) {
        return <div className="animate-pulse h-12 bg-muted/50 rounded-lg w-full max-w-sm" />;
    }

    const effectiveHealth = fallbackHealth ?? health;
    const isOnline = Boolean(effectiveHealth && effectiveHealth.status === "healthy");

    return (
        <div className="flex flex-col gap-3 bg-card/40 backdrop-blur-md border border-border/50 p-4 rounded-xl shadow-sm max-w-xl">
            <div className="flex items-center gap-3">
                <div className="p-2 bg-secondary rounded-full">
                    <ActivitySquare className="w-5 h-5 text-primary" />
                </div>
                <div>
                    <p className="text-sm font-medium leading-none mb-1">后端服务器</p>
                    <div className="flex items-center gap-2">
                        {isOnline ? <Badge variant="success">在线</Badge> : <Badge variant="destructive">离线</Badge>}
                        {effectiveHealth?.platform && (
                            <span className="text-xs text-muted-foreground uppercase">{effectiveHealth.platform}</span>
                        )}
                    </div>
                </div>
            </div>

            {isOnline && effectiveHealth && (
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-secondary rounded-full">
                        <AppWindow className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                        <p className="text-sm font-medium leading-none mb-1">浏览器运行环境</p>
                        <div className="flex items-center gap-2">
                            {effectiveHealth.browser_detected ? (
                                <Badge variant="success">已连接</Badge>
                            ) : (
                                <Badge variant="warning">未找到</Badge>
                            )}
                            {effectiveHealth.user_data_detected && (
                                <Badge variant="secondary" className="text-[10px] px-1.5 h-4">配置正常</Badge>
                            )}
                        </div>
                    </div>
                </div>
            )}

            <div className="text-[11px] text-muted-foreground border-t pt-2 space-y-1">
                <div>debug api: <span className="font-mono">{API_BASE_URL}</span></div>
                <div>debug react-query: {error ? "error" : "ok"}{queryError instanceof Error ? ` | ${queryError.message}` : ""}</div>
                <div>debug fallback: {fallbackError ? `error | ${fallbackError}` : (fallbackHealth ? "ok" : "empty")}</div>
                <div>debug last-check: {lastCheckAt || "-"}</div>
            </div>
        </div>
    );
}
