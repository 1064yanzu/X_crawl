"use client";
import { BarChart3 } from "lucide-react";

export function TaskRuntimeMetrics({
    qualityState,
    runtimeMetrics,
}: {
    qualityState?: string;
    runtimeMetrics?: Record<string, number>;
}) {
    const metrics = runtimeMetrics ?? {};
    return (
        <div className="bg-card border rounded-xl p-5 shadow-sm flex flex-col justify-center">
            <p className="text-xs text-muted-foreground font-semibold uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <BarChart3 className="w-4 h-4" /> 运行质量指标
            </p>
            <div className="text-sm space-y-1">
                <p>
                    质量状态: <span className="font-semibold">{qualityState ?? "complete"}</span>
                </p>
                <p className="text-muted-foreground">
                    超时: {(metrics.search_packet_timeouts ?? 0) + (metrics.reply_packet_timeouts ?? 0)} ·
                    软重试: {metrics.soft_retries ?? 0} ·
                    硬刷新: {metrics.hard_refreshes ?? 0}
                </p>
            </div>
        </div>
    );
}

