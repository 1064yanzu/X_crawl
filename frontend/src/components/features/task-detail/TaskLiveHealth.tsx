"use client";
import { ShieldAlert } from "lucide-react";
import { TaskOut } from "@/services/api";

function n(value: unknown): number {
    return typeof value === "number" ? value : 0;
}

export function TaskLiveHealth({ task }: { task: TaskOut }) {
    const live = task.live_metrics ?? {};
    const timeoutTotal = n(live.search_packet_timeouts) + n(live.reply_packet_timeouts);

    return (
        <div className="rounded-md border bg-card p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <ShieldAlert className="h-4 w-4 text-amber-500" />
                实时健康指标
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground md:grid-cols-4">
                <Stat label="超时总数" value={timeoutTotal} />
                <Stat label="软重试" value={n(live.soft_retries)} />
                <Stat label="硬刷新" value={n(live.hard_refreshes)} />
                <Stat label="风控命中" value={n(live.risk_hits)} />
                <Stat label="节流触发" value={n(live.resource_throttle_hits)} />
                <Stat label="高压触发" value={n(live.resource_critical_hits)} />
                <Stat label="主机 CPU" value={n(live.host_cpu_percent)} suffix="%" />
                <Stat label="进程 CPU" value={n(live.process_cpu_percent)} suffix="%" />
            </div>
        </div>
    );
}

function Stat({ label, value, suffix = "" }: { label: string; value: number; suffix?: string }) {
    return (
        <div className="rounded-md border bg-muted/20 px-3 py-3">
            <div className="text-[10px] uppercase tracking-[0.16em]">{label}</div>
            <div className="mt-1 font-mono text-sm text-foreground">{value}{suffix}</div>
        </div>
    );
}
