"use client";
import * as React from "react";
import {
    Monitor, Check, Loader2, AlertTriangle, RefreshCw, Sparkles, ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { api, BrowserInfo, BrowserListResponse } from "@/services/api";
import { cn } from "@/lib/utils";

const BROWSER_ICONS: Record<string, string> = {
    chrome: "🌐",
    chrome_canary: "🐤",
    edge: "🔷",
    brave: "🦁",
    arc: "🌈",
    chromium: "⚙️",
    vivaldi: "🎨",
    opera: "🔴",
    uc: "🟠",
    quark: "🔵",
    firefox: "🦊",
    safari: "🧭",
};

function getBrowserIcon(id: string): string {
    return BROWSER_ICONS[id] || "🌐";
}

function getSessionModeLabel(mode: string) {
    if (mode === "attached_browser") return "接管真实浏览器";
    if (mode === "crawler_profile") return "爬虫专用 Profile";
    return "尚未建立会话";
}

function BrowserCard({
    browser,
    isSelected,
    onSelect,
    isSelecting,
}: {
    browser: BrowserInfo;
    isSelected: boolean;
    onSelect: (id: string) => void;
    isSelecting: boolean;
}) {
    const isIncompatible = !browser.compatible;

    return (
        <button
            type="button"
            onClick={() => !isIncompatible && onSelect(browser.id)}
            disabled={isIncompatible || isSelecting}
            className={cn(
 "group relative w-full rounded-lg border-2 p-4 text-left transition-all duration-200",
 "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary hover:shadow-sm",
                isSelected
                    ? "border-primary bg-primary/6 shadow-sm"
                    : isIncompatible
                        ? "cursor-not-allowed border-border bg-muted/20 opacity-60"
                        : "cursor-pointer border-border bg-card hover:border-primary/30 hover:bg-primary/[0.02]",
            )}
        >
            {isSelected ? (
                <div className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
                    <Check className="h-3.5 w-3.5" />
                </div>
            ) : null}

            <div className="flex items-start gap-3">
                <span className="mt-0.5 text-2xl" role="img" aria-label={browser.name}>
                    {getBrowserIcon(browser.id)}
                </span>
                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-sm font-semibold text-foreground">{browser.name}</h4>
                        {isSelected ? <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">当前使用</span> : null}
                        {isIncompatible ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600">
                                <AlertTriangle className="h-2.5 w-2.5" />
                                不兼容
                            </span>
                        ) : null}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                        {browser.engine === "chromium" ? "Chromium 内核" : browser.engine === "firefox" ? "Gecko 内核" : browser.engine} 引擎
                    </p>
                    <p className="mt-1.5 truncate font-mono text-[11px] text-muted-foreground/70" title={browser.path}>
                        {browser.path}
                    </p>
                    {isIncompatible ? (
                        <p className="mt-2 text-[11px] text-amber-600/90">仅 Chromium 内核浏览器可被 DrissionPage 接管。</p>
                    ) : null}
                </div>
            </div>
        </button>
    );
}

export function BrowserSelector() {
    const { push } = useToast();
    const [data, setData] = React.useState<BrowserListResponse | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [selecting, setSelecting] = React.useState(false);
    const [selectedId, setSelectedId] = React.useState<string>("");

    const fetchBrowsers = React.useCallback(async () => {
        setLoading(true);
        try {
            const result = await api.browsers.list();
            setData(result);
            setSelectedId(result.selected_id);
        } catch (err) {
            console.error("获取浏览器列表失败:", err);
            push({ type: "error", title: "获取浏览器列表失败" });
        } finally {
            setLoading(false);
        }
    }, [push]);

    React.useEffect(() => {
        void fetchBrowsers();
    }, [fetchBrowsers]);

    const handleSelect = async (browserId: string) => {
        if (selecting) return;
        const newId = browserId === selectedId ? "" : browserId;
        setSelecting(true);
        try {
            const result = await api.browsers.select(newId);
            setSelectedId(newId);
            push({ type: "success", title: result.message });
        } catch (err) {
            push({ type: "error", title: "切换浏览器失败", description: err instanceof Error ? err.message : String(err) });
        } finally {
            setSelecting(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在检测系统已安装的浏览器...
            </div>
        );
    }

    if (!data || data.browsers.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 py-10 text-center">
                <Monitor className="mb-3 h-10 w-10 text-muted-foreground/30" />
                <p className="text-sm font-medium text-foreground">未检测到任何浏览器</p>
                <p className="mt-1 text-xs text-muted-foreground">请确认已安装 Chrome、Edge 或其它 Chromium 内核浏览器。</p>
                <Button variant="outline" size="sm" className="mt-4 rounded-md" onClick={() => void fetchBrowsers()}>
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                    重新检测
                </Button>
            </div>
        );
    }

    const compatibleCount = data.browsers.filter((browser) => browser.compatible).length;

    return (
        <div className="space-y-4">
            <div className="rounded-lg border border-border bg-muted/20 p-4 shadow-sm">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                        <h4 className="text-sm font-semibold text-foreground">当前浏览器会话</h4>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">
                            {getSessionModeLabel(data.session_mode)}
                            {data.headless ? " · Headless" : " · 有界面"}
                            {data.browser_alive ? " · 运行中" : " · 未启动"}
                        </p>
                    </div>
                    {data.last_login_failure_reason ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[10px] font-medium text-amber-600">
                            <AlertTriangle className="h-3 w-3" /> 最近登录失败
                        </span>
                    ) : (
                        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] font-medium text-emerald-700 dark:text-emerald-300">
                            <ShieldCheck className="h-3 w-3" /> 最近登录正常
                        </span>
                    )}
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <InfoTile label="实际用户目录" value={data.effective_user_data_path || "未启动后端浏览器时暂不可见"} mono />
                    <InfoTile label="爬虫专用目录" value={data.crawler_profile_path} mono />
                    <InfoTile label="最近检查时间" value={data.last_login_check_at || data.last_login_success_at || "暂无"} />
                    <InfoTile label="页面状态" value={data.last_page_state || "暂无"} />
                </div>

                {data.last_login_failure_reason ? (
                    <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                        最近失败原因：{data.last_login_failure_reason}
                    </div>
                ) : null}
            </div>

            <button
                type="button"
                onClick={() => void handleSelect("")}
                disabled={selecting}
                className={cn(
 "group relative w-full rounded-lg border-2 p-4 text-left transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary hover:shadow-sm",
                    !selectedId ? "border-primary bg-primary/6 shadow-sm" : "border-border bg-card hover:border-primary/30",
                )}
            >
                <div className="flex items-center gap-3">
                    <div className={cn("flex h-10 w-10 items-center justify-center rounded-md", !selectedId ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground")}>
                        <Sparkles className="h-5 w-5" />
                    </div>
                    <div className="flex-1">
                        <div className="flex items-center gap-2">
                            <h4 className="text-sm font-semibold text-foreground">自动检测</h4>
                            {!selectedId ? <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">当前模式</span> : null}
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground">自动选择系统中首个可用的 Chromium 内核浏览器。若开启“优先复用用户目录”，独立启动失败时会自动回退到隔离 Profile；稳定复用真实登录态更推荐调试端口接管。</p>
                    </div>
                    {!selectedId ? (
                        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                            <Check className="h-3.5 w-3.5" />
                        </div>
                    ) : null}
                </div>
            </button>

            <div className="flex items-center gap-3 px-1">
                <div className="h-px flex-1 bg-border/50" />
                <span className="shrink-0 text-xs text-muted-foreground">检测到 {data.browsers.length} 个浏览器，其中 {compatibleCount} 个兼容</span>
                <div className="h-px flex-1 bg-border/50" />
            </div>

            <div className="grid gap-3">
                {data.browsers.map((browser) => (
                    <BrowserCard
                        key={browser.id}
                        browser={browser}
                        isSelected={browser.id === selectedId}
                        onSelect={handleSelect}
                        isSelecting={selecting}
                    />
                ))}
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border bg-background p-4 shadow-sm">
                <p className="text-xs leading-5 text-muted-foreground">切换浏览器路径后，建议重启爬虫服务再发起新任务。</p>
                <Button variant="ghost" size="sm" onClick={() => void fetchBrowsers()} disabled={loading} className="rounded-md text-muted-foreground">
                    <RefreshCw className={cn("mr-1 h-3 w-3", loading && "animate-spin")} />
                    刷新
                </Button>
            </div>
        </div>
    );
}

function InfoTile({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
    return (
        <div className="rounded-md border border-border bg-background p-3 shadow-sm">
            <p className="text-[11px] text-muted-foreground">{label}</p>
            <p className={cn("mt-1 break-all text-sm text-foreground", mono && "font-mono text-[12px]")}>{value}</p>
        </div>
    );
}
