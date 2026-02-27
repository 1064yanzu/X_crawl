"use client";
import { ShieldAlert } from "lucide-react";
import { TaskOut } from "@/services/api";

function n(v: unknown): number {
    return typeof v === "number" ? v : 0;
}

export function TaskLiveHealth({ task }: { task: TaskOut }) {
    const live = task.live_metrics ?? {};
    const timeoutTotal = n(live.search_packet_timeouts) + n(live.reply_packet_timeouts);

    return (
        <div className="rounded-xl border bg-card p-4 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <ShieldAlert className="h-4 w-4 text-amber-500" />
                实时健康指标
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground md:grid-cols-4">
                <Stat label="超时" value={timeoutTotal} />
                <Stat label="软重试" value={n(live.soft_retries)} />
                <Stat label="硬刷新" value={n(live.hard_refreshes)} />
                <Stat label="风控命中" value={n(live.risk_hits)} />
                <Stat label="节流触发" value={n(live.resource_throttle_hits)} />
                <Stat label="高压触发" value={n(live.resource_critical_hits)} />
                <Stat label="主机CPU%" value={n(live.host_cpu_percent)} />
                <Stat label="进程CPU%" value={n(live.process_cpu_percent)} />
            </div>
        </div>
    );
}

function Stat({ label, value }: { label: string; value: number }) {
    return (
        <div className="rounded-lg border bg-muted/20 px-2 py-2">
            <div className="text-[10px] uppercase tracking-wider">{label}</div>
            <div className="mt-1 font-mono text-sm text-foreground">{value}</div>
        </div>
    );
}
