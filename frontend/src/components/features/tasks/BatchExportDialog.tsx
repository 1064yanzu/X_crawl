"use client";

import * as React from "react";
import { Download, FileSpreadsheet, FileText, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/services/api";

type ExportFormat = "csv" | "excel_single" | "excel_per_task";

export function BatchExportDialog({
    open,
    taskIds,
    onClose,
    onSuccess,
    onError,
}: {
    open: boolean;
    taskIds: string[];
    onClose: () => void;
    onSuccess: (message: string) => void;
    onError: (message: string) => void;
}) {
    const [format, setFormat] = React.useState<ExportFormat>("excel_per_task");
    const [exporting, setExporting] = React.useState(false);

    const handleExport = async () => {
        if (taskIds.length === 0) return;
        setExporting(true);
        try {
            if (format === "csv") {
                await api.export.batchDownloadCsv(taskIds);
            } else if (format === "excel_single") {
                await api.export.batchDownloadExcel(taskIds, "single");
            } else {
                await api.export.batchDownloadExcel(taskIds, "per_task");
            }
            onSuccess(`已导出 ${taskIds.length} 个任务的数据`);
            onClose();
        } catch (err) {
            onError(err instanceof Error ? err.message : String(err));
        } finally {
            setExporting(false);
        }
    };

    if (!open) return null;

    const FORMAT_OPTIONS: { value: ExportFormat; label: string; desc: string; icon: React.ReactNode }[] = [
        {
            value: "excel_per_task",
            label: "Excel（每任务一个 Sheet）",
            desc: "每个任务导出为独立的 Sheet，方便分别查看和分析",
            icon: <FileSpreadsheet className="h-4 w-4" />,
        },
        {
            value: "excel_single",
            label: "Excel（合并到一个 Sheet）",
            desc: "所有任务数据合并到一个 Sheet，附带来源标注列",
            icon: <FileSpreadsheet className="h-4 w-4" />,
        },
        {
            value: "csv",
            label: "CSV（合并文件）",
            desc: "所有任务合并导出为一个 CSV 文件，兼容各类数据工具",
            icon: <FileText className="h-4 w-4" />,
        },
    ];

    return (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-lg rounded-2xl border bg-card p-6 shadow-xl">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                        <div className="rounded-full bg-primary/10 p-2 text-primary">
                            <Download className="h-4 w-4" />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold">批量导出数据</h3>
                            <p className="text-sm text-muted-foreground">
                                已选择 {taskIds.length} 个任务
                            </p>
                        </div>
                    </div>
                    <Button variant="ghost" size="sm" className="rounded-lg" onClick={onClose} disabled={exporting}>
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                <div className="mt-5 space-y-2.5">
                    {FORMAT_OPTIONS.map((opt) => (
                        <label
                            key={opt.value}
                            className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-colors ${
                                format === opt.value
                                    ? "border-primary bg-primary/5"
                                    : "border-border/60 bg-background/60 hover:border-border"
                            }`}
                        >
                            <input
                                type="radio"
                                name="export-format"
                                value={opt.value}
                                checked={format === opt.value}
                                onChange={() => setFormat(opt.value)}
                                className="mt-0.5 accent-primary"
                            />
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2 text-sm font-medium">
                                    {opt.icon}
                                    {opt.label}
                                </div>
                                <p className="mt-0.5 text-xs text-muted-foreground">{opt.desc}</p>
                            </div>
                        </label>
                    ))}
                </div>

                <div className="mt-5 flex items-center justify-end gap-2">
                    <Button variant="outline" size="sm" className="rounded-xl" onClick={onClose} disabled={exporting}>
                        取消
                    </Button>
                    <Button size="sm" className="rounded-xl" onClick={() => void handleExport()} disabled={exporting}>
                        {exporting ? (
                            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        ) : (
                            <Download className="mr-1.5 h-3.5 w-3.5" />
                        )}
                        {exporting ? "导出中..." : "开始导出"}
                    </Button>
                </div>
            </div>
        </div>
    );
}
