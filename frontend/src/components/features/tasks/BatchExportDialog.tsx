"use client";

import * as React from "react";
import { Copy, Download, FileSpreadsheet, FileText, Loader2, X, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, ExportEstimateResponse } from "@/services/api";

type ExportFormat = "csv" | "excel_single" | "excel_per_task";

function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatNumber(n: number): string {
    return n.toLocaleString("zh-CN");
}

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
    const [deduplicate, setDeduplicate] = React.useState(false);
    const [exporting, setExporting] = React.useState(false);
    const [estimate, setEstimate] = React.useState<ExportEstimateResponse | null>(null);
    const [estimateLoading, setEstimateLoading] = React.useState(false);
    const [progress, setProgress] = React.useState<{ loaded: number; total: number | null } | null>(null);
    const abortRef = React.useRef<AbortController | null>(null);

    const deduplicateHint = format === "excel_per_task"
        ? "会在每个任务各自的 Sheet 内去重，避免单个任务内的重复帖子和评论。"
        : "会在最终合并导出的结果中去重，跨任务重复的数据也只保留一条。";

    // 对话框打开时获取预估信息
    React.useEffect(() => {
        if (!open || taskIds.length === 0) {
            setEstimate(null);
            return;
        }
        let cancelled = false;
        setEstimateLoading(true);
        api.export.batchEstimate(taskIds)
            .then((data) => {
                if (!cancelled) setEstimate(data);
            })
            .catch(() => {
                // 预估失败不影响导出功能
                if (!cancelled) setEstimate(null);
            })
            .finally(() => {
                if (!cancelled) setEstimateLoading(false);
            });
        return () => { cancelled = true; };
    }, [open, taskIds]);

    const handleExport = async () => {
        if (taskIds.length === 0) return;
        setExporting(true);
        setProgress(null);
        const controller = new AbortController();
        abortRef.current = controller;
        const opts = {
            signal: controller.signal,
            onProgress: (loaded: number, total: number | null) => {
                setProgress({ loaded, total });
            },
        };
        try {
            if (format === "csv") {
                await api.export.batchDownloadCsv(taskIds, deduplicate, opts);
            } else if (format === "excel_single") {
                await api.export.batchDownloadExcel(taskIds, "single", deduplicate, opts);
            } else {
                await api.export.batchDownloadExcel(taskIds, "per_task", deduplicate, opts);
            }
            onSuccess(`已导出 ${taskIds.length} 个任务的数据`);
            onClose();
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            if (msg !== "导出已取消") {
                onError(msg);
            }
        } finally {
            setExporting(false);
            setProgress(null);
            abortRef.current = null;
        }
    };

    const handleCancel = () => {
        if (abortRef.current) {
            abortRef.current.abort();
        }
    };

    if (!open) return null;

    const estimatedSize = estimate
        ? format === "csv"
            ? estimate.estimated_csv_bytes
            : estimate.estimated_excel_bytes
        : null;

    const progressPercent = progress?.total
        ? Math.min(99, Math.round((progress.loaded / progress.total) * 100))
        : null;

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

                {/* 数据量预估信息 */}
                {(estimateLoading || estimate) && (
                    <div className="mt-4 rounded-xl border border-border/60 bg-muted/30 px-4 py-3">
                        {estimateLoading ? (
                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                正在估算数据量...
                            </div>
                        ) : estimate && (
                            <div className="space-y-1.5">
                                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                                    <BarChart3 className="h-3.5 w-3.5 text-primary" />
                                    数据量预估
                                </div>
                                <div className="grid grid-cols-3 gap-3 text-xs text-muted-foreground">
                                    <div>
                                        <span className="text-foreground font-medium">
                                            {formatNumber(estimate.total_tweets)}
                                        </span>{" "}
                                        条推文
                                    </div>
                                    <div>
                                        <span className="text-foreground font-medium">
                                            {formatNumber(estimate.total_replies)}
                                        </span>{" "}
                                        条评论
                                    </div>
                                    <div>
                                        共{" "}
                                        <span className="text-foreground font-medium">
                                            {formatNumber(estimate.total_rows)}
                                        </span>{" "}
                                        行
                                    </div>
                                </div>
                                {estimatedSize != null && estimatedSize > 0 && (
                                    <p className="text-xs text-muted-foreground">
                                        预估文件大小约 {formatBytes(estimatedSize)}
                                    </p>
                                )}
                            </div>
                        )}
                    </div>
                )}

                <div className="mt-4 space-y-2.5">
                    {FORMAT_OPTIONS.map((opt) => (
                        <label
                            key={opt.value}
                            className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-colors ${
                                format === opt.value
                                    ? "border-primary bg-primary/5"
                                    : "border-border/60 bg-background/60 hover:border-border"
                            } ${exporting ? "pointer-events-none opacity-60" : ""}`}
                        >
                            <input
                                type="radio"
                                name="export-format"
                                value={opt.value}
                                checked={format === opt.value}
                                onChange={() => setFormat(opt.value)}
                                className="mt-0.5 accent-primary"
                                disabled={exporting}
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

                <label
                    className={`mt-4 flex cursor-pointer items-center gap-3 rounded-xl border p-3.5 transition-colors ${
                        deduplicate
                            ? "border-primary bg-primary/5"
                            : "border-border/60 bg-background/60 hover:border-border"
                    } ${exporting ? "pointer-events-none opacity-60" : ""}`}
                >
                    <input
                        type="checkbox"
                        checked={deduplicate}
                        onChange={(e) => setDeduplicate(e.target.checked)}
                        className="h-4 w-4 rounded border-input accent-primary"
                        disabled={exporting}
                    />
                    <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 text-sm font-medium">
                            <Copy className="h-4 w-4" />
                            导出时去重
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                            {deduplicateHint}
                        </p>
                    </div>
                </label>

                {/* 导出进度条 */}
                {exporting && (
                    <div className="mt-4 space-y-2">
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span className="flex items-center gap-1.5">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                {progress
                                    ? progressPercent != null
                                        ? `正在下载... ${progressPercent}%`
                                        : `正在下载... ${formatBytes(progress.loaded)}`
                                    : "正在生成导出文件..."
                                }
                            </span>
                            {progress && (
                                <span>{formatBytes(progress.loaded)}</span>
                            )}
                        </div>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                            {progressPercent != null ? (
                                <div
                                    className="h-full rounded-full bg-primary transition-all duration-300"
                                    style={{ width: `${progressPercent}%` }}
                                />
                            ) : (
                                <div className="h-full w-1/3 animate-pulse rounded-full bg-primary/60" />
                            )}
                        </div>
                    </div>
                )}

                <div className="mt-5 flex items-center justify-end gap-2">
                    {exporting ? (
                        <Button
                            variant="outline"
                            size="sm"
                            className="rounded-xl"
                            onClick={handleCancel}
                        >
                            取消导出
                        </Button>
                    ) : (
                        <Button variant="outline" size="sm" className="rounded-xl" onClick={onClose}>
                            取消
                        </Button>
                    )}
                    <Button
                        size="sm"
                        className="rounded-xl"
                        onClick={() => void handleExport()}
                        disabled={exporting}
                    >
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
