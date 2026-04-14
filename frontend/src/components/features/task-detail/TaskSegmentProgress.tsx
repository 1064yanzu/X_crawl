"use client";
import { SplitSquareVertical } from "lucide-react";
import { TaskOut } from "@/services/api";

export function TaskSegmentProgress({ task }: { task: TaskOut }) {
    const progress = task.segment_progress;
    if (!progress?.enabled || progress.total_segments <= 1) {
        return null;
    }

    const completed = Math.max(0, Math.min(progress.completed_segments, progress.total_segments));
    const pct = Math.min(100, Math.round((completed / progress.total_segments) * 100));
    const platformLabel = task.platform === "weibo" ? "微博" : "X";

    return (
        <div className="rounded-xl border bg-card p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <SplitSquareVertical className="h-4 w-4 text-primary" />
                {platformLabel} 时间分段进度
            </div>
            <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>已完成 {completed}/{progress.total_segments} 段</span>
                    <span className="font-mono">{pct}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-blue-500 transition-all duration-500" style={{ width: `${pct}%` }} />
                </div>
                <div className="text-xs text-muted-foreground">
                    当前区间：
                    <span className="ml-1 font-mono text-foreground">
                        {progress.current_since ?? "--"} ~ {progress.current_until ?? "--"}
                    </span>
                </div>
            </div>
        </div>
    );
}
