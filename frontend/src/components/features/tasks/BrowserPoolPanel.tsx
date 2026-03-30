"use client";

import * as React from "react";
import { Cpu, Loader2, Minus, Monitor, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useBrowserPool } from "@/hooks/useBrowserPool";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

/**
 * 浏览器并发状态面板
 *
 * 展示浏览器池实时状态并支持 +/- 动态调整并发数。
 * 设计为放在任务列表页顶部。
 */
export function BrowserPoolPanel() {
    const { data, isLoading, isResizing, resize } = useBrowserPool();
    const { push } = useToast();
    const [resizingDirection, setResizingDirection] = React.useState<-1 | 1 | null>(null);
    const configuredMax = data?.configured_max_size ?? 1;
    const actualPoolMax = data?.max_size ?? configuredMax;
    const crossPlatformEnabled = Boolean(data?.cross_platform_concurrent);
    const activeXAccounts = data?.active_x_accounts ?? 0;
    const effectiveXLimit = data?.effective_x_concurrency_limit ?? configuredMax;

    const handleResize = async (delta: -1 | 1) => {
        if (!data) return;
        const next = configuredMax + delta;
        if (next < 1 || next > 10) return;

        setResizingDirection(delta);
        try {
            const result = await resize(next);
            push({
                type: "success",
                title: result.message,
            });
        } catch (err) {
            push({
                type: "error",
                title: "调整并发数失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setResizingDirection(null);
        }
    };

    if (isLoading || !data) {
        return (
            <Card className="rounded-2xl border-border/60 bg-card/90 p-4 shadow-sm">
                <div className="flex items-center gap-3">
                    <Skeleton className="h-10 w-10 rounded-xl" />
                    <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-24" />
                        <Skeleton className="h-3 w-40" />
                    </div>
                </div>
            </Card>
        );
    }

    return (
        <Card className="overflow-hidden rounded-2xl border-border/60 bg-card/90 shadow-sm">
            <div className="p-4">
                {/* 标题行 */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10">
                            <Monitor className="h-4.5 w-4.5 text-indigo-500" />
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-foreground">浏览器并发</h3>
                            <p className="text-[11px] text-muted-foreground">
                                配置 {configuredMax} · 实际槽位上限 {actualPoolMax}
                                {crossPlatformEnabled ? " · 已开启跨平台并发" : ""}
                            </p>
                            <p className="text-[11px] text-muted-foreground">
                                X 实际并发 {effectiveXLimit} · 活跃账号 {activeXAccounts}
                            </p>
                        </div>
                    </div>

                    {/* 并发数调整器 */}
                    <div className="flex items-center gap-1.5">
                        <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8 rounded-xl"
                            disabled={isResizing || configuredMax <= 1}
                            onClick={() => void handleResize(-1)}
                            title="减少单平台并发上限"
                        >
                            {resizingDirection === -1 ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                                <Minus className="h-3.5 w-3.5" />
                            )}
                        </Button>
                        <span className="inline-flex h-8 min-w-[40px] items-center justify-center rounded-xl border border-border/60 bg-background px-2 text-sm font-bold tabular-nums text-foreground">
                            {configuredMax}
                        </span>
                        <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8 rounded-xl"
                            disabled={isResizing || configuredMax >= 10}
                            onClick={() => void handleResize(1)}
                            title="增加单平台并发上限"
                        >
                            {resizingDirection === 1 ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                                <Plus className="h-3.5 w-3.5" />
                            )}
                        </Button>
                    </div>
                </div>

                {/* Slot 详情 */}
                {data.slots.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                        {data.slots.map((slot) => {
                            const isActive = Object.keys(slot.platforms).length > 0;
                            const platformLabels = Object.entries(slot.platforms).map(
                                ([platform, taskId]) => `${platform}:${taskId.slice(0, 6)}`
                            );

                            return (
                                <div
                                    key={slot.slot_id}
                                    className={cn(
                                        "flex items-center gap-2 rounded-xl border px-3 py-2 text-xs transition-colors",
                                        isActive
                                            ? "border-emerald-200/70 bg-emerald-50/50 dark:border-emerald-600/25 dark:bg-emerald-900/15"
                                            : "border-border/50 bg-muted/20",
                                    )}
                                >
                                    {/* 存活指示灯 */}
                                    <span
                                        className={cn(
                                            "inline-block h-2 w-2 rounded-full",
                                            slot.alive
                                                ? "bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.4)]"
                                                : "bg-zinc-300 dark:bg-zinc-600",
                                        )}
                                    />

                                    <span className="font-medium text-foreground">
                                        #{slot.slot_id}
                                    </span>

                                    {isActive ? (
                                        <span className="text-muted-foreground">
                                            {platformLabels.join(", ")}
                                        </span>
                                    ) : (
                                        <span className="text-muted-foreground/60">空闲</span>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    <p className="mt-3 text-xs text-muted-foreground/60">
                        暂无浏览器实例，任务启动后将自动创建。
                    </p>
                )}
            </div>

            {/* 底部提示 */}
            <div className="border-t border-border/40 bg-muted/10 px-4 py-2">
                <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <Cpu className="h-3 w-3" />
                    这里调整的是单平台并发上限；X 任务实际并发还会受活跃账号数限制。推荐单平台 1–3，并保持一号一任务。
                </p>
            </div>
        </Card>
    );
}
