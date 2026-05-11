"use client";

import * as React from "react";
import { Copy, AlertTriangle, Loader2, X, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/services/api";
import type { MergePreviewResponse } from "@/services/api";
import { cn } from "@/lib/utils";

export function MergeTasksDialog({
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
    const [preview, setPreview] = React.useState<MergePreviewResponse | null>(null);
    const [loadingPreview, setLoadingPreview] = React.useState(false);
    const [merging, setMerging] = React.useState(false);

    const taskIdsStr = taskIds.join(",");

    React.useEffect(() => {
        if (open && taskIdsStr.length > 0) {
            setLoadingPreview(true);
            setPreview(null);
            api.tasks.mergePreview(taskIdsStr.split(","))
                .then(setPreview)
                .catch((err) => onError(err instanceof Error ? err.message : String(err)))
                .finally(() => setLoadingPreview(false));
        }
    }, [open, taskIdsStr, onError]);

    const handleMerge = async () => {
        if (!preview || preview.groups.length === 0) return;
        setMerging(true);
        try {
            const res = await api.tasks.merge(taskIds);
            onSuccess(res.message);
            onClose();
        } catch (err) {
            onError(err instanceof Error ? err.message : String(err));
        } finally {
            setMerging(false);
        }
    };

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-2xl rounded-md border bg-card p-6 shadow-xl max-h-[90vh] flex flex-col">
                <div className="flex items-center justify-between shrink-0 mb-4">
                    <div className="flex items-center gap-2.5">
                        <div className="rounded-full bg-primary/10 p-2 text-primary">
                            <Copy className="h-4 w-4" />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold">合并任务</h3>
                            <p className="text-sm text-muted-foreground">
                                已选择 {taskIds.length} 个任务
                            </p>
                        </div>
                    </div>
                    <Button variant="ghost" size="sm" className="rounded-lg" onClick={onClose} disabled={merging}>
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                <div className="flex-1 overflow-y-auto mb-4">
                    {loadingPreview ? (
                        <div className="flex h-32 flex-col items-center justify-center gap-2 text-muted-foreground">
                            <Loader2 className="h-6 w-6 animate-spin" />
                            <p className="text-sm">正在分析可合并任务...</p>
                        </div>
                    ) : preview ? (
                        preview.groups.length === 0 ? (
                            <div className="flex h-32 flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-muted/20 text-muted-foreground">
                                <AlertTriangle className="h-6 w-6 opacity-80" />
                                <p className="text-sm">所选任务中没有可合并的分组</p>
                                <p className="text-xs opacity-80">需要至少 2 个「已完成/停止/失败」状态且关键词存在交集的任务才可合并</p>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-4 text-amber-800 dark:border-amber-500/20 dark:text-amber-300">
                                    <div className="flex items-start gap-2">
                                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                                        <div className="text-sm leading-relaxed">
                                            <p className="font-semibold mb-1">合并操作不可逆</p>
                                            <ul className="list-disc pl-4 space-y-1">
                                                <li>合并后优先保留关键词更完整的任务为主任务；同等情况下再保留更早创建的任务。</li>
                                                <li>推文会根据 ID 自动去重。</li>
                                                <li>被吸收的其他源任务及其抓取记录将会被永久删除。</li>
                                            </ul>
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-3">
                                    <h4 className="text-sm font-medium text-foreground">
                                        将执行 {preview.mergeable_group_count} 组合并操作（涉及 {preview.total_mergeable_tasks} 个任务）
                                    </h4>
                                    {preview.groups.map((group, idx) => (
                                        <div key={idx} className="rounded-md border bg-card overflow-hidden">
                                            <div className="bg-muted/30 px-4 py-3 border-b flex items-center justify-between">
                                                <div className="flex items-center gap-2 min-w-0">
                                                    <span className="font-semibold text-foreground truncate">{group.keyword}</span>
                                                    <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary uppercase">
                                                        {group.platform}
                                                    </span>
                                                    <span className="shrink-0 rounded-full bg-muted-foreground/10 px-2 py-0.5 text-[10px] text-muted-foreground">
                                                        {group.task_count} 个任务
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-3 text-sm shrink-0">
                                                    <div className="text-right">
                                                        <span className="text-xs text-muted-foreground mr-1.5">去重前</span>
                                                        <span className="tabular-nums font-medium line-through opacity-70">{group.total_tweets}</span>
                                                    </div>
                                                    <div className="text-right text-emerald-600 dark:text-emerald-400 font-medium">
                                                        <span className="text-xs text-muted-foreground/80 mr-1.5 line-through-none text-muted-foreground">去重预估</span>
                                                        <span className="tabular-nums">{group.estimated_unique_tweets}</span>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="p-0">
                                                <ul className="divide-y text-sm">
                                                    {group.tasks_summary.map((t) => (
                                                        <li key={t.task_id} className={cn("px-4 py-2.5 flex items-center gap-3", t.is_target ? "bg-primary/5" : "")}>
                                                            {t.is_target ? (
                                                                <CheckCircle2 className="h-4 w-4 text-primary shrink-0" />
                                                            ) : (
                                                                <span title="将被删除"><X className="h-4 w-4 text-destructive/70 shrink-0" /></span>
                                                            )}
                                                            <div className="min-w-0 flex-1 flex flex-col">
                                                                <div className="flex items-center gap-2">
                                                                    <code className="text-[11px] text-muted-foreground">{t.task_id.slice(0, 8)}</code>
                                                                    <span className="text-muted-foreground text-xs">{t.status}</span>
                                                                </div>
                                                                <div className="text-xs text-muted-foreground mt-0.5">
                                                                    创建于 {t.created_at ? new Date(t.created_at).toLocaleString() : '--'}
                                                                </div>
                                                            </div>
                                                            <div className="text-right font-medium tabular-nums shrink-0">
                                                                {t.result_count} 条
                                                            </div>
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                                {preview.non_mergeable_task_ids.length > 0 && (
                                    <p className="text-xs text-muted-foreground">
                                        提示：另有 {preview.non_mergeable_task_ids.length} 个选中任务不满足合并条件（处于活跃状态或没有可关联关键词）将被忽略。
                                    </p>
                                )}
                            </div>
                        )
                    ) : null}
                </div>

                <div className="flex items-center justify-end gap-2 pt-4 border-t shrink-0 mt-auto">
                    <Button variant="outline" size="sm" className="rounded-md" onClick={onClose} disabled={merging}>
                        取消
                    </Button>
                    <Button 
                        size="sm" 
                        className="rounded-md bg-primary hover:bg-primary/90 text-primary-foreground" 
                        onClick={() => void handleMerge()} 
                        disabled={merging || !preview || preview.groups.length === 0}
                    >
                        {merging ? (
                            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        ) : (
                            <Copy className="mr-1.5 h-3.5 w-3.5" />
                        )}
                        {merging ? "合并中..." : "确认合并任务"}
                    </Button>
                </div>
            </div>
        </div>
    );
}
