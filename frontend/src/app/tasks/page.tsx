"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Clock3, Database, Loader2, TerminalSquare } from "lucide-react";
import { api } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageHeader } from "@/components/ui/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { TaskBatchActions } from "@/components/features/tasks/TaskBatchActions";
import { TaskFiltersBar } from "@/components/features/tasks/TaskFiltersBar";
import { TaskListCard } from "@/components/features/tasks/TaskListCard";
import { TaskPreviewDrawer, TaskPreviewPanel } from "@/components/features/tasks/TaskPreview";
import { useTasksQuery } from "@/hooks/useTasks";
import { useTaskListState } from "@/hooks/useTaskListState";
import { useToast } from "@/components/ui/toast";
import { getPlatformMeta } from "@/lib/platformRegistry";

export default function TasksPage() {
    const { data, isLoading, refetch } = useTasksQuery(5000);
    const tasks = React.useMemo(() => data ?? [], [data]);
    const { push } = useToast();
    const router = useRouter();
    const [resumingId, setResumingId] = React.useState<string | null>(null);
    const [deleteId, setDeleteId] = React.useState<string | null>(null);
    const [batchAction, setBatchAction] = React.useState<"resume" | "delete" | null>(null);
    const [confirmBatchDelete, setConfirmBatchDelete] = React.useState(false);

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
        completedCount,
        riskCount,
        hasSearch,
        previewTask,
        activeTaskId,
        setActiveTaskId,
        activePreviewTask,
        selectedSet,
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
                    <div className="grid gap-3 md:grid-cols-3">
                        <StatCard label="全部任务" value={tasks.length} hint="包含历史记录与当前队列" icon={Database} />
                        <StatCard label="运行中 / 暂停" value={activeCount} hint="需要优先关注的任务" icon={Loader2} tone="primary" />
                        <StatCard label="异常 / 风控" value={riskCount} hint={`累计完成 ${completedCount} 个任务`} icon={Clock3} tone={riskCount > 0 ? "warning" : "success"} />
                    </div>
                </PageHeader>

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
                    resumableSelectedCount={resumableSelectedCount}
                    allVisibleSelected={allVisibleSelected}
                    busyAction={batchAction}
                    onToggleSelectAll={toggleSelectAllVisible}
                    onClearSelection={clearSelection}
                    onBatchResume={() => void handleBatchResume()}
                    onBatchDelete={() => setConfirmBatchDelete(true)}
                />

                <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_380px] xl:items-start">
                    <div className="min-w-0 space-y-4">
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
                            <div className="grid gap-4">
                                {searchedTasks.map((task) => (
                                    <TaskListCard
                                        key={task.task_id}
                                        task={task}
                                        density={density}
                                        selected={selectedSet.has(task.task_id)}
                                        focused={activeTaskId === task.task_id}
                                        busyAction={batchAction}
                                        resumingId={resumingId}
                                        onHover={setActiveTaskId}
                                        onSelect={toggleSelectTask}
                                        onPreview={openPreview}
                                        onResume={(taskId) => void handleResume(taskId)}
                                        onDelete={setDeleteId}
                                    />
                                ))}
                            </div>
                        )}
                    </div>

                    <aside className="hidden xl:block">
                        <div className="sticky top-24">
                            <TaskPreviewPanel
                                task={activePreviewTask}
                                resumingId={resumingId}
                                onResume={(taskId) => void handleResume(taskId)}
                                onDelete={setDeleteId}
                            />
                        </div>
                    </aside>
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

            <TaskPreviewDrawer
                task={previewTask}
                resumingId={resumingId}
                onClose={closePreview}
                onResume={(taskId) => void handleResume(taskId)}
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
