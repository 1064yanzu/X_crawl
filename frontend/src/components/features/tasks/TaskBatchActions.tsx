import { Copy, Download, Loader2, MessageCircleMore, PauseCircle, PlayCircle, RefreshCcw, RotateCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export function TaskBatchActions({
    searchedCount,
    selectedCount,
    exportableSelectedCount,
    resumableSelectedCount,
    backfillableSelectedCount,
    recrawlableSelectedCount,
    mergeableSelectedCount,
    hasActiveTasks,
    allVisibleSelected,
    busyAction,
    onToggleSelectAll,
    onClearSelection,
    onPauseAll,
    onResumeAll,
    onBatchResume,
    onBatchCommentBackfill,
    onBatchRecrawl,
    onBatchExport,
    onBatchDelete,
    onBatchMerge,
}: {
    searchedCount: number;
    selectedCount: number;
    exportableSelectedCount: number;
    resumableSelectedCount: number;
    backfillableSelectedCount: number;
    recrawlableSelectedCount: number;
    mergeableSelectedCount: number;
    hasActiveTasks: boolean;
    allVisibleSelected: boolean;
    busyAction: "resume" | "resumeAll" | "pauseAll" | "backfill" | "recrawl" | "delete" | "export" | "merge" | null;
    onToggleSelectAll: () => void;
    onClearSelection: () => void;
    onPauseAll: () => void;
    onResumeAll: () => void;
    onBatchResume: () => void;
    onBatchCommentBackfill: () => void;
    onBatchRecrawl: () => void;
    onBatchExport: () => void;
    onBatchDelete: () => void;
    onBatchMerge: () => void;
}) {
    if (searchedCount === 0) return null;

    return (
        <div className="rounded-[1.5rem] border border-border/60 bg-card/90 p-4 shadow-sm backdrop-blur-sm sm:p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                    <h2 className="text-lg font-semibold text-foreground">批量操作</h2>
                    <p className="text-sm text-muted-foreground">
                        当前筛出 {searchedCount} 个任务，已选择 {selectedCount} 个；其中可导出 {exportableSelectedCount} 个，可继续 {resumableSelectedCount} 个，可补采评论 {backfillableSelectedCount} 个，可复爬 {recrawlableSelectedCount} 个，可合并 {mergeableSelectedCount} 个。
                    </p>
                </div>

                <div className="flex flex-wrap gap-2">
                    <Button
                        className="rounded-xl bg-amber-600 text-white hover:bg-amber-700 dark:bg-amber-600 dark:hover:bg-amber-700"
                        onClick={onPauseAll}
                        disabled={!hasActiveTasks || busyAction !== null}
                    >
                        {busyAction === "pauseAll" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <PauseCircle className="mr-1.5 h-3.5 w-3.5" />}
                        一键暂停全部
                    </Button>
                    <Button
                        className="rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 dark:bg-emerald-600 dark:hover:bg-emerald-700"
                        onClick={onResumeAll}
                        disabled={busyAction !== null}
                    >
                        {busyAction === "resumeAll" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <PlayCircle className="mr-1.5 h-3.5 w-3.5" />}
                        一键恢复全部
                    </Button>
                    <div className="mx-1 hidden h-8 w-px bg-border/60 sm:block" />
                    <Button variant="outline" className="rounded-xl" onClick={onToggleSelectAll}>
                        {allVisibleSelected ? "取消全选" : "全选当前结果"}
                    </Button>
                    <Button variant="ghost" className="rounded-xl" onClick={onClearSelection} disabled={selectedCount === 0}>
                        清空选择
                    </Button>
                    <Button
                        variant="outline"
                        className="rounded-xl"
                        onClick={onBatchExport}
                        disabled={exportableSelectedCount === 0 || busyAction !== null}
                    >
                        {busyAction === "export" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1.5 h-3.5 w-3.5" />}
                        批量导出
                    </Button>
                    <Button
                        variant="outline"
                        className="rounded-xl"
                        onClick={onBatchResume}
                        disabled={resumableSelectedCount === 0 || busyAction !== null}
                    >
                        {busyAction === "resume" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="mr-1.5 h-3.5 w-3.5" />}
                        批量继续
                    </Button>
                    <Button
                        variant="outline"
                        className="rounded-xl"
                        onClick={onBatchCommentBackfill}
                        disabled={backfillableSelectedCount === 0 || busyAction !== null}
                    >
                        {busyAction === "backfill" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <MessageCircleMore className="mr-1.5 h-3.5 w-3.5" />}
                        批量补采评论
                    </Button>
                    <Button
                        variant="outline"
                        className="rounded-xl"
                        onClick={onBatchRecrawl}
                        disabled={recrawlableSelectedCount === 0 || busyAction !== null}
                    >
                        {busyAction === "recrawl" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="mr-1.5 h-3.5 w-3.5" />}
                        批量复爬
                    </Button>
                    <Button
                        variant="outline"
                        className="rounded-xl"
                        onClick={onBatchMerge}
                        disabled={mergeableSelectedCount < 2 || busyAction !== null}
                    >
                        {busyAction === "merge" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Copy className="mr-1.5 h-3.5 w-3.5" />}
                        批量合并
                    </Button>
                    <Button
                        variant="outline"
                        className="rounded-xl border-red-300 text-red-700 hover:bg-red-50 dark:border-red-500/30 dark:text-red-300 dark:hover:bg-red-500/10"
                        onClick={onBatchDelete}
                        disabled={selectedCount === 0 || busyAction !== null}
                    >
                        {busyAction === "delete" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-1.5 h-3.5 w-3.5" />}
                        删除选中
                    </Button>
                </div>
            </div>
        </div>
    );
}
