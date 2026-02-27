"use client";
import { Activity, Clock3, Gauge, ListOrdered, PlugZap } from "lucide-react";
import type { ReactNode } from "react";
import { TaskOut } from "@/services/api";

function metricValue(value: unknown, fallback = "0") {
    if (typeof value === "number") return Number.isFinite(value) ? value.toLocaleString() : fallback;
    if (typeof value === "string") return value;
    return fallback;
}

export function TaskLiveKpiBar({ task, connected }: { task: TaskOut; connected: boolean }) {
    const live = task.live_metrics ?? {};
    const pressure = typeof live.resource_pressure_state === "string" ? live.resource_pressure_state : "normal";
    return (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiItem icon={<Gauge className="h-4 w-4" />} label="推文速率(15s)" value={`${metricValue(live.tweets_per_min_15s)} / min`} />
            <KpiItem icon={<Activity className="h-4 w-4" />} label="回复速率(15s)" value={`${metricValue(live.replies_per_min_15s)} / min`} />
            <KpiItem icon={<Clock3 className="h-4 w-4" />} label="运行时长" value={`${metricValue(live.elapsed_sec)}s`} />
            <KpiItem icon={<Clock3 className="h-4 w-4" />} label="空闲时长" value={`${metricValue(live.idle_sec)}s`} />
            <KpiItem icon={<Gauge className="h-4 w-4" />} label="主机内存" value={`${metricValue(live.host_mem_used_percent)}%`} />
            <KpiItem icon={<Gauge className="h-4 w-4" />} label="进程内存" value={`${metricValue(live.process_rss_mb)} MB`} />
            <KpiItem icon={<Gauge className="h-4 w-4" />} label="节流倍数" value={`${metricValue(live.crawl_throttle_factor, "1")}x (${pressure})`} />
            <KpiItem
                icon={connected ? <PlugZap className="h-4 w-4" /> : <ListOrdered className="h-4 w-4" />}
                label={task.status === "pending" ? "队列位置" : "实时通道"}
                value={task.status === "pending" ? `${task.queue_position ?? "-"}` : connected ? "SSE" : "轮询"}
            />
        </div>
    );
}

function KpiItem({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
    return (
        <div className="rounded-xl border bg-card px-3 py-2.5 shadow-sm">
            <div className="mb-1 flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
                {icon}
                <span>{label}</span>
            </div>
            <div className="font-mono text-sm font-semibold text-foreground">{value}</div>
        </div>
    );
}
