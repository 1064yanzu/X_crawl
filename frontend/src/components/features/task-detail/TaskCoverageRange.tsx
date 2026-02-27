"use client";
import { CalendarRange } from "lucide-react";
import { TaskOut } from "@/services/api";

function fmt(value: unknown) {
    if (typeof value !== "string" || !value) return "--";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "--";
    return dt.toLocaleString();
}

function span(value: unknown) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "0";
    return value.toLocaleString();
}

export function TaskCoverageRange({ task }: { task: TaskOut }) {
    const coverage = task.time_coverage ?? {};

    return (
        <div className="rounded-xl border bg-card p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <CalendarRange className="h-4 w-4 text-primary" />
                推文/评论覆盖时间范围
            </div>
            <div className="grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
                <RangeRow
                    title="推文覆盖"
                    start={fmt(coverage.tweet_start_at)}
                    end={fmt(coverage.tweet_end_at)}
                    extra={`跨度 ${span(coverage.tweet_span_hours)}h · 样本 ${span(coverage.tweet_ts_count)}`}
                />
                <RangeRow
                    title="评论覆盖"
                    start={fmt(coverage.reply_start_at)}
                    end={fmt(coverage.reply_end_at)}
                    extra={`跨度 ${span(coverage.reply_span_hours)}h · 样本 ${span(coverage.reply_ts_count)}`}
                />
                <RangeRow
                    title="合并覆盖"
                    start={fmt(coverage.combined_start_at)}
                    end={fmt(coverage.combined_end_at)}
                    extra={`跨度 ${span(coverage.combined_span_hours)}h`}
                />
            </div>
        </div>
    );
}

function RangeRow({ title, start, end, extra }: { title: string; start: string; end: string; extra: string }) {
    return (
        <div className="rounded-lg border bg-muted/20 px-3 py-2">
            <div className="font-medium text-foreground">{title}</div>
            <div className="mt-1 font-mono text-[11px]">{start} ~ {end}</div>
            <div className="mt-1 text-[11px]">{extra}</div>
        </div>
    );
}
