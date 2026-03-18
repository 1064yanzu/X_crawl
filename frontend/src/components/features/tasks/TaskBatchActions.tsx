import { Download, Loader2, MessageCircleMore, RefreshCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export function TaskBatchActions({
    searchedCount,
    selectedCount,
    exportableSelectedCount,
    resumableSelectedCount,
    backfillableSelectedCount,
    allVisibleSelected,
    busyAction,
    onToggleSelectAll,
    onClearSelection,
    onBatchResume,
    onBatchCommentBackfill,
    onBatchExport,
    onBatchDelete,
}: {
    searchedCount: number;
    selectedCount: number;
    exportableSelectedCount: number;
    resumableSelectedCount: number;
    backfillableSelectedCount: number;
    allVisibleSelected: boolean;
    busyAction: "resume" | "backfill" | "delete" | "export" | null;
    onToggleSelectAll: () => void;
    onClearSelection: () => void;
    onBatchResume: () => void;
    onBatchCommentBackfill: () => void;
    onBatchExport: () => void;
    onBatchDelete: () => void;
}) {
    if (searchedCount === 0) return null;

    return (
        <div className="rounded-[1.5rem] border border-border/60 bg-card/90 p-4 shadow-sm backdrop-blur-sm sm:p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                    <h2 className="text-lg font-semibold text-foreground">批量操作</h2>
                    <p className="text-sm text-muted-foreground">
                        当前筛出 {searchedCount} 个任务，已选择 {selectedCount} 个；其中可导出 {exportableSelectedCount} 个，可继续 {resumableSelectedCount} 个，可补采评论 {backfillableSelectedCount} 个。
                    </p>
                </div>

                <div className="flex flex-wrap gap-2">
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
