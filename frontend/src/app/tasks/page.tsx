"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Clock3, Database, Loader2, Pause, TerminalSquare } from "lucide-react";
import { api } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageHeader } from "@/components/ui/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { TaskBatchActions } from "@/components/features/tasks/TaskBatchActions";
import { BatchExportDialog } from "@/components/features/tasks/BatchExportDialog";
import { MergeTasksDialog } from "@/components/features/tasks/MergeTasksDialog";
import { TaskFiltersBar } from "@/components/features/tasks/TaskFiltersBar";
import { TaskListCard } from "@/components/features/tasks/TaskListCard";
import { TaskPreviewDrawer, TaskPreviewPanel } from "@/components/features/tasks/TaskPreview";
import { BrowserPoolPanel } from "@/components/features/tasks/BrowserPoolPanel";
import { useTasksQuery } from "@/hooks/useTasks";
import { useTaskListState } from "@/hooks/useTaskListState";
import { useToast } from "@/components/ui/toast";
import { getPlatformMeta } from "@/lib/platformRegistry";
import { canCreateCommentBackfillFromTask, canRecrawlTask } from "@/lib/task-ui";
import { cn } from "@/lib/utils";

export default function TasksPage() {
    const { data, isLoading, refetch } = useTasksQuery(5000);
    const tasks = React.useMemo(() => data ?? [], [data]);
    const { push } = useToast();
    const router = useRouter();
    const [resumingId, setResumingId] = React.useState<string | null>(null);
    const [backfillingId, setBackfillingId] = React.useState<string | null>(null);
    const [deleteId, setDeleteId] = React.useState<string | null>(null);
    const [recrawlingId, setRecrawlingId] = React.useState<string | null>(null);
    const [batchAction, setBatchAction] = React.useState<"resume" | "resumeAll" | "pauseAll" | "backfill" | "recrawl" | "delete" | "export" | null>(null);
    const [confirmBatchDelete, setConfirmBatchDelete] = React.useState(false);
    const [showBatchExport, setShowBatchExport] = React.useState(false);
    const [showMergeTasks, setShowMergeTasks] = React.useState(false);

    const {
        searchInputRef,
        activePlatform,
        setActivePlatform,
        query,
        setQuery,
        sortMode,
        setSortMode,
        density,
        setDensity,
        searchedTasks,
        platformCounts,
        activeCount,
        runningCount,
        pausedCount,
        completedCount,
        riskCount,
        hasSearch,
        previewTask,
        activeTaskId,
        setActiveTaskId,
        activePreviewTask,
        selectedSet,
        selectedTasks,
        selectedCount,
        resumableSelectedTasks,
        resumableSelectedCount,
        allVisibleSelected,
        clearSelection,
        toggleSelectTask,
        toggleSelectAllVisible,
        openPreview,
        closePreview,
    } = useTaskListState(tasks, (taskId) => router.push(`/tasks/${taskId}`));

    const backfillableSelectedTasks = React.useMemo(
        () => selectedTasks.filter((task) => canCreateCommentBackfillFromTask(task)),
        [selectedTasks],
    );
    const backfillableSelectedCount = backfillableSelectedTasks.length;

    const exportableSelectedTasks = React.useMemo(
        () => selectedTasks.filter((task) => task.result_count > 0),
        [selectedTasks],
    );
    const exportableSelectedCount = exportableSelectedTasks.length;

    const recrawlableSelectedTasks = React.useMemo(
        () => selectedTasks.filter((task) => canRecrawlTask(task)),
        [selectedTasks],
    );
    const recrawlableSelectedCount = recrawlableSelectedTasks.length;

    const mergeableSelectedTasks = React.useMemo(
        () => selectedTasks.filter((task) => ["done", "stopped", "failed"].includes(task.status)),
        [selectedTasks],
    );
    const mergeableSelectedCount = mergeableSelectedTasks.length;

    const handleDelete = async (taskId: string) => {
        try {
            await api.tasks.delete(taskId);
            if (previewTask?.task_id === taskId) {
                closePreview();
            }
            push({ type: "success", title: "任务已删除" });
            await refetch();
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "删除任务失败" });
        }
    };

    const handleResume = async (taskId: string) => {
        setResumingId(taskId);
        try {
            await api.tasks.resume(taskId);
            push({ type: "success", title: "任务已重新加入队列" });
            await refetch();
        } catch (err) {
            console.error(err);
            push({
                type: "error",
                title: "恢复任务失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setResumingId(null);
        }
    };

    const handleCreateCommentBackfill = async (taskIds: string[], options?: { openFirst?: boolean }) => {
        if (taskIds.length === 0) {
            push({ type: "info", title: "当前没有可补采评论的任务" });
            return;
        }

        const openFirst = options?.openFirst ?? false;
        const loadingTaskId = taskIds.length === 1 ? taskIds[0] : null;
        setBackfillingId(loadingTaskId);
        if (taskIds.length > 1) {
            setBatchAction("backfill");
        }

        try {
            const result = await api.commentBackfill.fromTasks({
                taskIds,
                replyDepth: 2,
                maxRepliesPerTweet: 0,
                queueName: taskIds.length > 1 ? "评论补采批次" : undefined,
            });

            const skippedCount = result.sources.filter((item) => item.status === "skipped").length;
            const description = result.queued
                ? `已创建 ${result.created_count} 个评论补采任务，并自动进入顺序队列。`
                : "已创建评论补采任务，默认补采到二级评论。";

            push({
                type: "success",
                title: result.queued ? "评论补采队列已创建" : "评论补采任务已创建",
                description: skippedCount > 0 ? `${description} 另有 ${skippedCount} 个任务因不符合条件被跳过。` : description,
            });

            clearSelection();
            await refetch();

            if (openFirst && result.tasks[0]) {
                router.push(`/tasks/${result.tasks[0].task_id}`);
            }
        } catch (err) {
            console.error(err);
            push({
                type: "error",
                title: "创建评论补采任务失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setBackfillingId(null);
            setBatchAction((current) => (current === "backfill" ? null : current));
        }
    };

    const handlePauseAll = async () => {
        setBatchAction("pauseAll");
        try {
            const result = await api.tasks.pauseAll();
            const pausedCount = result.paused.length;
            const stoppedCount = result.stopped.length;
            const totalAffected = pausedCount + stoppedCount;
            const failedCount = result.failed.length;

            if (totalAffected > 0) {
                await refetch();
            }

            if (totalAffected === 0 && failedCount === 0) {
                push({ type: "info", title: "没有正在运行的任务", description: "当前没有需要暂停的活跃任务。" });
            } else if (failedCount === 0) {
                const parts: string[] = [];
                if (pausedCount > 0) parts.push(`${pausedCount} 个运行中任务已暂停`);
                if (stoppedCount > 0) parts.push(`${stoppedCount} 个等待中任务已停止`);
                push({ type: "success", title: "一键暂停完成", description: parts.join("，") });
            } else {
                push({
                    type: totalAffected > 0 ? "info" : "error",
                    title: totalAffected > 0 ? `已暂停 ${totalAffected} 个任务` : "暂停失败",
                    description: `${failedCount} 个任务暂停失败，请稍后重试。`,
                });
            }
        } catch (err) {
            console.error(err);
            push({
                type: "error",
                title: "一键暂停失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setBatchAction(null);
        }
    };

    const scenarioDescriptions: Record<string, string> = {
        user_paused: "已恢复之前暂停的任务。",
        risk_control: "已恢复因风控暂停的任务，将自动重试。",
        mixed: "已恢复所有暂停的任务（包含主动暂停和风控暂停）。",
    };

    const handleResumeAll = async () => {
        setBatchAction("resumeAll");
        try {
            const result = await api.tasks.resumeAll();
            const resumedCount = result.resumed.length;
            const failedCount = result.failed.length;
            const scenario = result.scenario;

            if (resumedCount > 0) {
                await refetch();
            }

            if (resumedCount === 0 && failedCount === 0) {
                push({ type: "info", title: "没有需要恢复的任务", description: "所有任务均已完成或正在运行中。" });
            } else if (failedCount === 0) {
                push({
                    type: "success",
                    title: `已恢复 ${resumedCount} 个任务`,
                    description: scenarioDescriptions[scenario] ?? undefined,
                });
            } else {
                push({
                    type: resumedCount > 0 ? "info" : "error",
                    title: resumedCount > 0 ? `已恢复 ${resumedCount} 个任务` : "恢复失败",
                    description: `${failedCount} 个任务恢复失败，请稍后重试。`,
                });
            }
        } catch (err) {
            console.error(err);
            push({
                type: "error",
                title: "一键恢复失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setBatchAction(null);
        }
    };

    const handleBatchResume = async () => {
        if (resumableSelectedCount === 0) {
            push({ type: "info", title: "选中的任务里没有可继续的项目" });
            return;
        }

        const ids = resumableSelectedTasks.map((task) => task.task_id);
        setBatchAction("resume");

        try {
            const results = await Promise.allSettled(ids.map((taskId) => api.tasks.resume(taskId)));
            const successCount = results.filter((result) => result.status === "fulfilled").length;
            const failedCount = results.length - successCount;

            if (successCount > 0) {
                clearSelection();
                await refetch();
            }

            if (failedCount === 0) {
                push({ type: "success", title: `已恢复 ${successCount} 个任务` });
            } else {
                push({
                    type: successCount > 0 ? "info" : "error",
                    title: successCount > 0 ? `已恢复 ${successCount} 个任务` : "批量恢复失败",
                    description: `仍有 ${failedCount} 个任务未恢复成功，请稍后重试。`,
                });
            }
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "批量恢复失败" });
        } finally {
            setBatchAction(null);
        }
    };

    const handleRecrawl = async (taskId: string) => {
        setRecrawlingId(taskId);
        try {
            const result = await api.tasks.recrawl(taskId);
            push({
                type: "success",
                title: "增量复爬任务已创建",
                description: `排除 ${result.exclude_count} 条已有推文，新任务 ID: ${result.new_task_id.slice(0, 8)}`,
            });
            await refetch();
        } catch (err) {
            console.error(err);
            push({
                type: "error",
                title: "复爬任务创建失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setRecrawlingId(null);
        }
    };

    const handleBatchRecrawl = async () => {
        if (recrawlableSelectedCount === 0) {
            push({ type: "info", title: "选中的任务里没有可复爬的项目" });
            return;
        }

        const ids = recrawlableSelectedTasks.map((task) => task.task_id);
        setBatchAction("recrawl");

        try {
            const result = await api.tasks.recrawlBatch(ids);
            const createdCount = result.created.length;
            const skippedCount = result.skipped.length;

            if (createdCount > 0) {
                clearSelection();
                await refetch();
            }

            if (skippedCount === 0) {
                push({ type: "success", title: `已创建 ${createdCount} 个复爬任务` });
            } else {
                push({
                    type: createdCount > 0 ? "info" : "error",
                    title: createdCount > 0 ? `已创建 ${createdCount} 个复爬任务` : "批量复爬失败",
                    description: `${skippedCount} 个任务不符合条件被跳过。`,
                });
            }
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "批量复爬失败", description: err instanceof Error ? err.message : String(err) });
        } finally {
            setBatchAction(null);
        }
    };

    const handleBatchDelete = async () => {
        if (selectedCount === 0) return;

        const ids = Array.from(selectedSet);
        setBatchAction("delete");

        try {
            const results = await Promise.allSettled(ids.map((taskId) => api.tasks.delete(taskId)));
            const successIds = results
                .map((result, index) => (result.status === "fulfilled" ? ids[index] : null))
                .filter((taskId): taskId is string => Boolean(taskId));
            const failedCount = results.length - successIds.length;

            if (successIds.length > 0) {
                clearSelection();
                if (previewTask && successIds.includes(previewTask.task_id)) {
                    closePreview();
                }
                await refetch();
            }

            if (failedCount === 0) {
                push({ type: "success", title: `已删除 ${successIds.length} 个任务` });
            } else {
                push({
                    type: successIds.length > 0 ? "info" : "error",
                    title: successIds.length > 0 ? `已删除 ${successIds.length} 个任务` : "批量删除失败",
                    description: `仍有 ${failedCount} 个任务未删除成功，请稍后重试。`,
                });
            }
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "批量删除失败" });
        } finally {
            setBatchAction(null);
        }
    };

    return (
        <>
            <div className="space-y-6 pb-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
                <PageHeader
                    eyebrow="Task Center"
                    icon={Database}
                    title="采集队列"
                    description="查看和管理采集任务。"
                    actions={
                        <Link href="/">
                            <Button className="rounded-xl">
                                <TerminalSquare className="mr-2 h-4 w-4" />
                                新建任务
                            </Button>
                        </Link>
                    }
                >
                    <div className="grid gap-3 md:grid-cols-4">
                        <StatCard label="全部任务" value={tasks.length} hint="包含历史记录与当前队列" icon={Database} />
                        <StatCard label="运行中" value={runningCount} hint="正在执行或排队中" icon={Loader2} tone="primary" />
                        <StatCard label="已暂停" value={pausedCount} hint={pausedCount > 0 ? "有任务被暂停，可一键恢复" : "当前没有暂停的任务"} icon={Pause} tone={pausedCount > 0 ? "warning" : undefined} />
                        <StatCard label="异常 / 风控" value={riskCount} hint={`累计完成 ${completedCount} 个任务`} icon={Clock3} tone={riskCount > 0 ? "warning" : "success"} />
                    </div>
                </PageHeader>

                <BrowserPoolPanel />

                <TaskFiltersBar
                    activePlatform={activePlatform}
                    onPlatformChange={setActivePlatform}
                    platformCounts={platformCounts}
                    searchInputRef={searchInputRef}
                    query={query}
                    onQueryChange={setQuery}
                    sortMode={sortMode}
                    onSortModeChange={setSortMode}
                    density={density}
                    onDensityChange={setDensity}
                />

                <TaskBatchActions
                    searchedCount={searchedTasks.length}
                    selectedCount={selectedCount}
                    exportableSelectedCount={exportableSelectedCount}
                    resumableSelectedCount={resumableSelectedCount}
                    backfillableSelectedCount={backfillableSelectedCount}
                    recrawlableSelectedCount={recrawlableSelectedCount}
                    mergeableSelectedCount={mergeableSelectedCount}
                    hasActiveTasks={activeCount > 0}
                    allVisibleSelected={allVisibleSelected}
                    busyAction={batchAction}
                    onToggleSelectAll={toggleSelectAllVisible}
                    onClearSelection={clearSelection}
                    onPauseAll={() => void handlePauseAll()}
                    onResumeAll={() => void handleResumeAll()}
                    onBatchResume={() => void handleBatchResume()}
                    onBatchCommentBackfill={() => void handleCreateCommentBackfill(backfillableSelectedTasks.map((task) => task.task_id))}
                    onBatchRecrawl={() => void handleBatchRecrawl()}
                    onBatchExport={() => setShowBatchExport(true)}
                    onBatchDelete={() => setConfirmBatchDelete(true)}
                    onBatchMerge={() => setShowMergeTasks(true)}
                />

                <div className={density === "mini" ? "" : "grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_380px] xl:items-start"}>
                    <div className="min-w-0">
                        {isLoading && tasks.length === 0 ? (
                            <TaskListSkeleton />
                        ) : searchedTasks.length === 0 ? (
                            <EmptyState
                                icon={Database}
                                title={hasSearch ? "没有匹配的任务" : activePlatform === "all" ? "当前还没有采集任务" : `当前没有 ${getPlatformMeta(activePlatform).label} 任务`}
                                description={hasSearch
                                    ? "可以尝试修改关键词、切换平台或更换排序方式。"
                                    : activePlatform === "all"
                                        ? "从控制台创建第一个采集任务后，这里会开始记录实时状态和历史结果。"
                                        : "可以切换回全部平台，或直接创建该平台的新任务。"}
                                action={
                                    hasSearch ? (
                                        <Button variant="outline" className="rounded-xl" onClick={() => setQuery("")}>清空搜索</Button>
                                    ) : activePlatform === "all" ? (
                                        <Link href="/">
                                            <Button variant="outline" className="rounded-xl">去创建任务</Button>
                                        </Link>
                                    ) : (
                                        <Button variant="outline" className="rounded-xl" onClick={() => setActivePlatform("all")}>查看全部平台</Button>
                                    )
                                }
                            />
                        ) : (
                            <div className={cn(
                                "grid",
                                density === "mini" ? "gap-0.5 rounded-2xl border border-border/60 bg-card/90 p-2 shadow-sm" : density === "compact" ? "gap-2" : "gap-4",
                            )}>
                                {searchedTasks.map((task) => (
                                    <TaskListCard
                                        key={task.task_id}
                                        task={task}
                                        density={density}
                                        selected={selectedSet.has(task.task_id)}
                                        focused={activeTaskId === task.task_id}
                                        busyAction={batchAction}
                                        resumingId={resumingId}
                                        backfillingId={backfillingId}
                                        recrawlingId={recrawlingId}
                                        onHover={setActiveTaskId}
                                        onSelect={toggleSelectTask}
                                        onPreview={openPreview}
                                        onResume={(taskId) => void handleResume(taskId)}
                                        onCommentBackfill={(taskId) => void handleCreateCommentBackfill([taskId], { openFirst: true })}
                                        onRecrawl={(taskId) => void handleRecrawl(taskId)}
                                        onDelete={setDeleteId}
                                    />
                                ))}
                            </div>
                        )}
                    </div>

                    {density !== "mini" ? (
                        <aside className="hidden xl:block">
                            <div className="sticky top-24">
                                <TaskPreviewPanel
                                    task={activePreviewTask}
                                    resumingId={resumingId}
                                    backfillingId={backfillingId}
                                    recrawlingId={recrawlingId}
                                    onResume={(taskId) => void handleResume(taskId)}
                                    onCommentBackfill={(taskId) => void handleCreateCommentBackfill([taskId], { openFirst: true })}
                                    onRecrawl={(taskId) => void handleRecrawl(taskId)}
                                    onDelete={setDeleteId}
                                />
                            </div>
                        </aside>
                    ) : null}
                </div>

                <ConfirmDialog
                    open={Boolean(deleteId)}
                    title="确认删除任务？"
                    description="删除后该任务会从当前列表移除，已导出的文件不受影响。"
                    confirmText="删除"
                    cancelText="取消"
                    onCancel={() => setDeleteId(null)}
                    onConfirm={async () => {
                        if (!deleteId) return;
                        const id = deleteId;
                        setDeleteId(null);
                        await handleDelete(id);
                    }}
                />

                <ConfirmDialog
                    open={confirmBatchDelete}
                    title="确认批量删除所选任务？"
                    description={`当前将删除 ${selectedCount} 个任务。已导出的文件不会受影响，但这些任务会从当前列表移除。`}
                    confirmText="批量删除"
                    cancelText="取消"
                    onCancel={() => setConfirmBatchDelete(false)}
                    onConfirm={async () => {
                        setConfirmBatchDelete(false);
                        await handleBatchDelete();
                    }}
                />
            </div>

            <BatchExportDialog
                open={showBatchExport}
                taskIds={exportableSelectedTasks.map((task) => task.task_id)}
                onClose={() => setShowBatchExport(false)}
                onSuccess={(msg) => push({ type: "success", title: msg })}
                onError={(msg) => push({ type: "error", title: "批量导出失败", description: msg })}
            />

            <MergeTasksDialog
                open={showMergeTasks}
                taskIds={selectedTasks.map((task) => task.task_id)}
                onClose={() => setShowMergeTasks(false)}
                onSuccess={(msg) => {
                    push({ type: "success", title: "合并任务成功", description: msg });
                    clearSelection();
                    refetch();
                }}
                onError={(msg) => push({ type: "error", title: "合并任务失败", description: msg })}
            />

            <TaskPreviewDrawer
                task={previewTask}
                resumingId={resumingId}
                backfillingId={backfillingId}
                recrawlingId={recrawlingId}
                onClose={closePreview}
                onResume={(taskId) => void handleResume(taskId)}
                onCommentBackfill={(taskId) => void handleCreateCommentBackfill([taskId], { openFirst: true })}
                onRecrawl={(taskId) => void handleRecrawl(taskId)}
                onDelete={setDeleteId}
            />
        </>
    );
}

function TaskListSkeleton() {
    return (
        <div className="space-y-3">
            {[1, 2, 3].map((item) => (
                <Card key={item} className="rounded-[1.5rem] border border-border/60 bg-card/90 p-5 shadow-sm">
                    <div className="space-y-4">
                        <div className="flex items-center gap-2">
                            <Skeleton className="h-6 w-24 rounded-full" />
                            <Skeleton className="h-6 w-24 rounded-full" />
                        </div>
                        <Skeleton className="h-7 w-1/2" />
                        <div className="grid gap-3 md:grid-cols-4">
                            {[1, 2, 3, 4].map((meta) => (
                                <Skeleton key={meta} className="h-16 w-full" />
                            ))}
                        </div>
                    </div>
                </Card>
            ))}
        </div>
    );
}
