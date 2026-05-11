"use client";
import * as React from "react";
import { CheckCircle2, CircleAlert, PlugZap, AppWindow } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealthQuery } from "@/hooks/useHealth";
import { API_BASE_URL, HealthResponse } from "@/services/api";
import { cn } from "@/lib/utils";

function StatusDot({ ok }: { ok: boolean }) {
    return (
        <span
            aria-hidden
            className={cn(
                "relative inline-flex h-2 w-2 shrink-0 rounded-full",
                ok ? "bg-[var(--ok)]" : "bg-[var(--danger)]",
            )}
        >
            {ok ? (
                <span className="absolute inset-0 -z-10 animate-ping rounded-full bg-[var(--ok)] opacity-30" />
            ) : null}
        </span>
    );
}

export function ServerStatus() {
    const { data: health, isLoading, isError, error: queryError } = useHealthQuery();
    const [fallbackHealth, setFallbackHealth] = React.useState<HealthResponse | null>(null);
    const [fallbackError, setFallbackError] = React.useState<string>("");
    const [lastCheckAt, setLastCheckAt] = React.useState<string>("");
    const [showDetails, setShowDetails] = React.useState(false);

    React.useEffect(() => {
        const toMessage = (value: unknown) => (value instanceof Error ? value.message : String(value ?? "fallback failed"));
        const run = async () => {
            try {
                const resp = await fetch(`${API_BASE_URL}/health?t=${Date.now()}`, { cache: "no-store" });
                setLastCheckAt(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
                if (!resp.ok) {
                    setFallbackError(`HTTP ${resp.status}`);
                    return;
                }
                const data = (await resp.json()) as HealthResponse;
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

    const effective = fallbackHealth ?? health;
    const isOnline = Boolean(effective && effective.status === "healthy");
    const browserConnected = Boolean(effective?.browser_detected);
    const envReady = Boolean(effective?.user_data_detected);

    if (isLoading) {
        return (
            <section className="space-y-3">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
            </section>
        );
    }

    return (
        <section aria-labelledby="server-status-heading" className="space-y-5">
            <div className="flex items-baseline justify-between gap-3">
                <div>
                    <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-[color:var(--fg-subtle)]">
                        System dispatch
                    </p>
                    <h2
                        id="server-status-heading"
                        className="mt-1 flex items-center gap-3 font-serif text-[1.5rem] font-medium leading-tight tracking-tight text-foreground"
                    >
                        <StatusDot ok={isOnline} />
                        系统状态
                    </h2>
                </div>
                <p className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-[color:var(--fg-muted)]">
                    {isOnline ? "Online" : "Down"}
                </p>
            </div>

            <hr className="border-[var(--line)]" />

            <dl className="grid gap-x-6 gap-y-3 text-[13px] leading-6">
                <Row
                    icon={isOnline ? CheckCircle2 : CircleAlert}
                    label="后端服务"
                    value={isOnline ? "可用" : "不可用"}
                    hint={lastCheckAt ? `最近检查 ${lastCheckAt}` : "等待首次检查"}
                    tone={isOnline ? "ok" : "warn"}
                />
                <Row
                    icon={browserConnected ? PlugZap : AppWindow}
                    label="浏览器环境"
                    value={browserConnected ? "已连接" : "未连接"}
                    hint={envReady ? "本地配置已就绪" : "用户数据目录未就绪"}
                    tone={browserConnected ? "primary" : "default"}
                />
            </dl>

            <hr className="border-[var(--line)]" />

            <div className="grid grid-cols-3 gap-x-6 gap-y-1 text-[12px]">
                <Meta label="平台" value={effective?.platform ? effective.platform.toUpperCase() : "--"} />
                <Meta label="模式" value={browserConnected ? "已接入" : "等待启动"} />
                <Meta label="建议" value={isOnline ? (browserConnected ? "可发起采集" : "先配置浏览器") : "先检查服务"} />
            </div>

            <button
                type="button"
                onClick={() => setShowDetails((v) => !v)}
                className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-[color:var(--fg-muted)] underline-offset-[6px] transition-colors hover:text-[var(--accent)] hover:underline"
            >
                {showDetails ? "收起技术详情" : "展开技术详情"}
            </button>

            {showDetails ? (
                <div className="space-y-1 border-l border-[var(--line)] pl-4 text-[12px] leading-6 text-[color:var(--fg-muted)]">
                    <div>
                        API <span className="font-mono text-foreground">{API_BASE_URL}</span>
                    </div>
                    <div>
                        React Query · {isError ? `error${queryError instanceof Error ? ` | ${queryError.message}` : ""}` : "ok"}
                    </div>
                    <div>Fallback · {fallbackError ? `error | ${fallbackError}` : fallbackHealth ? "ok" : "idle"}</div>
                    <div>最近检查 · {lastCheckAt || "--"}</div>
                </div>
            ) : null}
        </section>
    );
}

function Row({
    icon: Icon,
    label,
    value,
    hint,
    tone,
}: {
    icon: React.ComponentType<{ className?: string }>;
    label: string;
    value: string;
    hint?: string;
    tone: "ok" | "warn" | "primary" | "default";
}) {
    const toneClass = {
        ok: "text-[var(--ok)]",
        warn: "text-[var(--warn)]",
        primary: "text-[var(--accent)]",
        default: "text-[color:var(--fg-muted)]",
    }[tone];

    return (
        <div className="flex items-baseline justify-between gap-4 border-b border-dashed border-[var(--line)] pb-2 last:border-b-0">
            <div className="flex items-center gap-2.5">
                <Icon className={cn("h-3.5 w-3.5", toneClass)} />
                <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-[color:var(--fg-muted)]">
                    {label}
                </span>
            </div>
            <div className="flex flex-col items-end gap-0.5">
                <span className="font-serif text-[15px] text-foreground">{value}</span>
                {hint ? (
                    <span className="text-[11px] text-[color:var(--fg-subtle)]">{hint}</span>
                ) : null}
            </div>
        </div>
    );
}

function Meta({ label, value }: { label: string; value: string }) {
    return (
        <div>
            <p className="font-mono text-[9.5px] uppercase tracking-[0.22em] text-[color:var(--fg-subtle)]">
                {label}
            </p>
            <p className="mt-0.5 text-[12.5px] text-foreground">{value}</p>
        </div>
    );
}
