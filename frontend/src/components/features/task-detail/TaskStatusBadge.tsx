"use client";
import type { LucideIcon } from "lucide-react";
import { CheckCircle2, Loader2, Pause, ShieldAlert, StopCircle, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { getRiskStateLabel } from "@/lib/task-ui";
import { cn } from "@/lib/utils";

type Props = {
    status: string;
    riskState: string;
    size?: "default" | "sm" | "xs";
    className?: string;
};

type BadgeMeta = {
    label: string;
    icon: LucideIcon;
    className: string;
};

function getMeta(status: string, riskState: string): BadgeMeta {
    const isRunning = status === "running" || status === "pending";
    const isPaused = status === "paused";
    const isRiskPaused = isPaused && riskState !== "none";

    if (isRunning) {
        return {
            label: status === "pending" ? "排队中" : "正在执行",
            icon: Loader2,
            className: "border-0 bg-blue-500/10 text-blue-700 dark:text-blue-300",
        };
    }
    if (isRiskPaused) {
        const riskLabel = getRiskStateLabel(riskState);
        return {
            label: `风控暂停 · ${riskLabel}`,
            icon: ShieldAlert,
            className: "border-0 bg-orange-500/10 text-orange-700 dark:text-orange-300",
        };
    }
    if (isPaused) {
        return {
            label: "已暂停",
            icon: Pause,
            className: "border-0 bg-amber-500/10 text-amber-700 dark:text-amber-300",
        };
    }
    if (status === "stopped") {
        return {
            label: "已终止",
            icon: StopCircle,
            className: "border-0 bg-slate-500/10 text-slate-700 dark:text-slate-300",
        };
    }
    if (status === "done") {
        return {
            label: "任务完成",
            icon: CheckCircle2,
            className: "border-0 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        };
    }
    if (status === "failed") {
        return {
            label: "任务失败",
            icon: XCircle,
            className: "border-0 bg-red-500/10 text-red-700 dark:text-red-300",
        };
    }
    return {
        label: status,
        icon: Pause,
        className: "border-border bg-background text-muted-foreground",
    };
}

export function TaskStatusBadge({ status, riskState, size = "default", className }: Props) {
    const meta = getMeta(status, riskState);
    const Icon = meta.icon;

    return (
        <Badge
            className={cn(
 "font-medium",
                size === "xs" ? "h-5 rounded px-1.5 text-[10px]" : size === "sm" ? "h-6 rounded-full px-2.5 text-[11px]" : "py-1 text-sm",
                meta.className,
                className,
            )}
        >
            <Icon className={cn(size === "xs" ? "mr-1 h-3 w-3" : "mr-1.5", size === "sm" ? "h-3.5 w-3.5" : size === "xs" ? "" : "h-4 w-4", (status === "running" || status === "pending") && "animate-spin")} />
            {meta.label}
        </Badge>
    );
}
