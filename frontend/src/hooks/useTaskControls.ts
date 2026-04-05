"use client";

import * as React from "react";
import { api, type TaskOut } from "@/services/api";
import { useToast } from "@/components/ui/toast";

export function useTaskControls(
    task: TaskOut | null,
    refetch: () => Promise<unknown>,
    setLiveControlState: React.Dispatch<React.SetStateAction<"pause" | "resume" | "stop" | null>>,
) {
    const { push } = useToast();
    const [exporting, setExporting] = React.useState<"csv" | "excel" | null>(null);
    const [controlling, setControlling] = React.useState<"pause" | "resume" | "stop" | null>(null);
    const [confirmStop, setConfirmStop] = React.useState(false);

    const handleExport = React.useCallback(async (format: "csv" | "excel") => {
        if (!task) return;
        setExporting(format);

        try {
            if (format === "csv") await api.export.downloadCsv(task.task_id);
            else await api.export.downloadExcel(task.task_id);
        } catch (err) {
            console.error("导出失败:", err);
            push({ type: "error", title: "导出失败", description: err instanceof Error ? err.message : String(err) });
        } finally {
            setTimeout(() => setExporting(null), 800);
        }
    }, [push, task]);

    const handleControl = React.useCallback(async (action: "pause" | "resume" | "stop") => {
        if (!task) return;
        setControlling(action);
        setLiveControlState(action);

        try {
            if (action === "pause") await api.tasks.pause(task.task_id);
            else if (action === "resume") {
                const concurrency = task.task_kind === "comment_backfill_group" ? (task.concurrency ?? 1) : undefined;
                await api.tasks.resume(task.task_id, concurrency && concurrency > 1 ? { concurrency } : undefined);
            }
            else await api.tasks.stop(task.task_id);

            await refetch();
            push({
                type: "success",
                title: action === "pause" ? "任务已暂停" : action === "resume" ? "任务已恢复" : "终止指令已发送",
            });
        } catch (err) {
            console.error(`操作失败 (${action}):`, err);
            push({ type: "error", title: "任务控制失败", description: err instanceof Error ? err.message : String(err) });
        } finally {
            setControlling(null);
            setLiveControlState(null);
        }
    }, [push, refetch, setLiveControlState, task]);

    return {
        exporting,
        controlling,
        confirmStop,
        setConfirmStop,
        handleExport,
        handleControl,
    };
}
