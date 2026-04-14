"use client";

import { CalendarRange, SplitSquareVertical } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { Platform, TimeSplitMode } from "@/services/api";

const MODE_OPTIONS: Array<{ value: TimeSplitMode; label: string; description: string }> = [
    { value: "inherit", label: "跟随默认", description: "使用设置页中的平台默认拆分策略。" },
    { value: "on", label: "强制拆分", description: "本任务按你指定的窗口天数切段执行。" },
    { value: "off", label: "不拆分", description: "本任务禁用时间拆分，即使默认开启也不拆。" },
];

export function TimeSplitControls({
    platform,
    hasTimeRange,
    mode,
    windowDays,
    maxSegments,
    onModeChange,
    onWindowDaysChange,
    onMaxSegmentsChange,
    defaultWindowDays,
    defaultMaxSegments,
    className,
}: {
    platform: Platform;
    hasTimeRange: boolean;
    mode: TimeSplitMode;
    windowDays: number;
    maxSegments: number;
    onModeChange: (value: TimeSplitMode) => void;
    onWindowDaysChange: (value: number) => void;
    onMaxSegmentsChange: (value: number) => void;
    defaultWindowDays: number;
    defaultMaxSegments: number;
    className?: string;
}) {
    const platformLabel = platform === "weibo" ? "微博" : "X";

    return (
        <div className={cn("rounded-2xl border border-border/60 bg-muted/20 p-4", className)}>
            <div className="flex items-start gap-3">
                <div className="rounded-xl bg-primary/10 p-2 text-primary">
                    <SplitSquareVertical className="h-4 w-4" />
                </div>
                <div className="flex-1">
                    <p className="font-medium text-foreground">时间拆分</p>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                        {hasTimeRange
                            ? `为本次${platformLabel}任务决定是否拆分时间范围。默认窗口 ${defaultWindowDays} 天，默认最大 ${defaultMaxSegments} 段。`
                            : "只有任务包含有效时间范围时，时间拆分才会生效。"}
                    </p>
                </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-3">
                {MODE_OPTIONS.map((option) => {
                    const active = mode === option.value;
                    return (
                        <button
                            key={option.value}
                            type="button"
                            disabled={!hasTimeRange}
                            onClick={() => onModeChange(option.value)}
                            className={cn(
                                "rounded-2xl border px-4 py-4 text-left transition-all duration-200",
                                active ? "border-primary/30 bg-primary/8 text-foreground shadow-sm" : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
                                !hasTimeRange && "cursor-not-allowed opacity-55 hover:border-border/70 hover:bg-card",
                            )}
                        >
                            <p className="font-medium">{option.label}</p>
                            <p className="mt-2 text-xs leading-5 text-muted-foreground">{option.description}</p>
                        </button>
                    );
                })}
            </div>

            {mode === "on" && hasTimeRange ? (
                <div className="mt-4 grid gap-4 border-t border-border/60 pt-4 md:grid-cols-2">
                    <div className="space-y-2">
                        <label className="flex items-center gap-2 text-sm font-medium text-foreground">
                            <CalendarRange className="h-4 w-4 text-primary" />
                            每段天数
                        </label>
                        <Input
                            type="number"
                            min={1}
                            max={365}
                            value={windowDays}
                            onChange={(event) => onWindowDaysChange(Number(event.target.value) || defaultWindowDays)}
                            className="h-11 rounded-xl bg-background"
                        />
                        <p className="text-xs text-muted-foreground">当前默认值 {defaultWindowDays} 天。</p>
                    </div>
                    <div className="space-y-2">
                        <label className="text-sm font-medium text-foreground">最大分段数</label>
                        <Input
                            type="number"
                            min={1}
                            max={2000}
                            value={maxSegments}
                            onChange={(event) => onMaxSegmentsChange(Number(event.target.value) || defaultMaxSegments)}
                            className="h-11 rounded-xl bg-background"
                        />
                        <p className="text-xs text-muted-foreground">高级项。当前默认值 {defaultMaxSegments} 段。</p>
                    </div>
                </div>
            ) : null}
        </div>
    );
}
