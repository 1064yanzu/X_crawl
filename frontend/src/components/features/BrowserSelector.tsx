"use client";
import * as React from "react";
import {
    Monitor, Check, Loader2, AlertTriangle, RefreshCw, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, BrowserInfo, BrowserListResponse } from "@/services/api";
import { cn } from "@/lib/utils";

// ── 浏览器图标映射（使用 emoji 作为轻量方案）─────────────────────────────────
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

// ── 浏览器卡片 ──────────────────────────────────────────────────────────────
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
            onClick={() => !isIncompatible && onSelect(browser.id)}
            disabled={isIncompatible || isSelecting}
            className={cn(
                "group relative w-full text-left p-4 rounded-xl border-2 transition-all duration-300",
                "hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                isSelected
                    ? "border-primary bg-primary/5 shadow-sm"
                    : isIncompatible
                        ? "border-border/30 bg-muted/20 opacity-60 cursor-not-allowed"
                        : "border-border/50 bg-card hover:border-primary/40 hover:bg-primary/[0.02] cursor-pointer",
            )}
        >
            {/* 选中指示器 */}
            {isSelected && (
                <div className="absolute top-3 right-3">
                    <div className="flex items-center justify-center w-6 h-6 rounded-full bg-primary text-primary-foreground">
                        <Check className="w-3.5 h-3.5" />
                    </div>
                </div>
            )}

            <div className="flex items-start gap-3">
                {/* 浏览器图标 */}
                <span className="text-2xl shrink-0 mt-0.5" role="img" aria-label={browser.name}>
                    {getBrowserIcon(browser.id)}
                </span>

                <div className="flex-1 min-w-0">
                    {/* 名称 + 标签 */}
                    <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="font-semibold text-sm text-foreground">{browser.name}</h4>
                        {isIncompatible && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-amber-500/10 text-amber-600 px-1.5 py-0.5 rounded-full border border-amber-500/20">
                                <AlertTriangle className="w-2.5 h-2.5" />
                                不兼容
                            </span>
                        )}
                        {isSelected && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-primary/10 text-primary px-1.5 py-0.5 rounded-full">
                                当前使用
                            </span>
                        )}
                    </div>

                    {/* 内核信息 */}
                    <p className="text-xs text-muted-foreground mt-1">
                        {browser.engine === "chromium" ? "Chromium 内核" :
                            browser.engine === "firefox" ? "Gecko 内核" : browser.engine} 引擎
                    </p>

                    {/* 路径 */}
                    <p className="text-[11px] text-muted-foreground/60 mt-1.5 font-mono truncate" title={browser.path}>
                        {browser.path}
                    </p>
                </div>
            </div>

            {/* 不兼容提示 */}
            {isIncompatible && (
                <p className="text-[11px] text-amber-600/80 mt-2 pl-9">
                    DrissionPage 仅支持 Chromium 内核浏览器，{browser.name} 不可用于爬取。
                </p>
            )}
        </button>
    );
}

// ── 主组件 ──────────────────────────────────────────────────────────────────
export function BrowserSelector() {
    const [data, setData] = React.useState<BrowserListResponse | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [selecting, setSelecting] = React.useState(false);
    const [selectedId, setSelectedId] = React.useState<string>("");
    const [message, setMessage] = React.useState<{ text: string; type: "success" | "error" } | null>(null);

    const fetchBrowsers = React.useCallback(async () => {
        setLoading(true);
        try {
            const result = await api.browsers.list();
            setData(result);
            setSelectedId(result.selected_id);
        } catch (err) {
            console.error("获取浏览器列表失败:", err);
        } finally {
            setLoading(false);
        }
    }, []);

    React.useEffect(() => {
        fetchBrowsers();
    }, [fetchBrowsers]);

    const handleSelect = async (browserId: string) => {
        if (selecting) return;

        // 点击已选中的 → 取消选择（恢复自动检测）
        const newId = browserId === selectedId ? "" : browserId;

        setSelecting(true);
        setMessage(null);
        try {
            const result = await api.browsers.select(newId);
            setSelectedId(newId);
            setMessage({
                text: result.message,
                type: "success",
            });
            // 3 秒后清除消息
            setTimeout(() => setMessage(null), 4000);
        } catch (err) {
            setMessage({
                text: `选择失败：${err instanceof Error ? err.message : String(err)}`,
                type: "error",
            });
        } finally {
            setSelecting(false);
        }
    };

    // ── 加载状态 ──
    if (loading) {
        return (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-6">
                <Loader2 className="w-4 h-4 animate-spin" />
                正在检测系统已安装的浏览器...
            </div>
        );
    }

    // ── 无数据 ──
    if (!data || data.browsers.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-8 text-center">
                <Monitor className="w-10 h-10 text-muted-foreground/30 mb-3" />
                <p className="text-sm text-muted-foreground">未检测到任何浏览器</p>
                <p className="text-xs text-muted-foreground/60 mt-1">请确认已安装 Chrome、Edge 或其他 Chromium 内核浏览器</p>
                <Button variant="outline" size="sm" className="mt-4" onClick={fetchBrowsers}>
                    <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                    重新检测
                </Button>
            </div>
        );
    }

    const compatibleCount = data.browsers.filter((b) => b.compatible).length;

    return (
        <div className="space-y-4">
            {/* 自动检测选项 */}
            <button
                onClick={() => handleSelect("")}
                disabled={selecting}
                className={cn(
                    "group relative w-full text-left p-4 rounded-xl border-2 transition-all duration-300",
                    "hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                    !selectedId
                        ? "border-primary bg-primary/5 shadow-sm"
                        : "border-border/50 bg-card hover:border-primary/40 cursor-pointer",
                )}
            >
                <div className="flex items-center gap-3">
                    <div className={cn(
                        "flex items-center justify-center w-10 h-10 rounded-xl transition-colors",
                        !selectedId ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
                    )}>
                        <Sparkles className="w-5 h-5" />
                    </div>
                    <div className="flex-1">
                        <div className="flex items-center gap-2">
                            <h4 className="font-semibold text-sm text-foreground">自动检测</h4>
                            {!selectedId && (
                                <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-primary/10 text-primary px-1.5 py-0.5 rounded-full">
                                    当前模式
                                </span>
                            )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                            自动选择系统中首个可用的 Chromium 内核浏览器
                        </p>
                    </div>
                    {!selectedId && (
                        <div className="flex items-center justify-center w-6 h-6 rounded-full bg-primary text-primary-foreground shrink-0">
                            <Check className="w-3.5 h-3.5" />
                        </div>
                    )}
                </div>
            </button>

            {/* 分隔线 + 统计 */}
            <div className="flex items-center gap-3 px-1">
                <div className="flex-1 h-px bg-border/50" />
                <span className="text-xs text-muted-foreground shrink-0">
                    检测到 {data.browsers.length} 个浏览器，{compatibleCount} 个兼容
                </span>
                <div className="flex-1 h-px bg-border/50" />
            </div>

            {/* 浏览器列表 */}
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

            {/* 操作反馈消息 */}
            {message && (
                <div
                    className={cn(
                        "flex items-center gap-2 px-4 py-3 rounded-lg text-sm transition-all animate-in fade-in slide-in-from-top-2 duration-300",
                        message.type === "success"
                            ? "bg-green-500/10 text-green-700 dark:text-green-400 border border-green-500/20"
                            : "bg-red-500/10 text-red-700 dark:text-red-400 border border-red-500/20",
                    )}
                >
                    {message.type === "success" ? (
                        <Check className="w-4 h-4 shrink-0" />
                    ) : (
                        <AlertTriangle className="w-4 h-4 shrink-0" />
                    )}
                    <span>{message.text}</span>
                </div>
            )}

            {/* 刷新按钮 */}
            <div className="flex items-center justify-between pt-1">
                <p className="text-xs text-muted-foreground">
                    切换浏览器后需重新启动爬虫服务才能生效
                </p>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={fetchBrowsers}
                    disabled={loading}
                    className="h-8 text-xs text-muted-foreground"
                >
                    <RefreshCw className={cn("w-3 h-3 mr-1", loading && "animate-spin")} />
                    刷新
                </Button>
            </div>
        </div>
    );
}
