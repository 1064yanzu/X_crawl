"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Database, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { TaskDetailHeader } from "@/components/features/task-detail/TaskDetailHeader";
import { TaskDetailOverview } from "@/components/features/task-detail/TaskDetailOverview";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/services/api";
import { useTaskLiveData } from "@/hooks/useTaskLiveData";
import { useTaskResultState } from "@/hooks/useTaskResultState";
import { useTaskControls } from "@/hooks/useTaskControls";
import { canCreateCommentBackfillFromTask, isTaskActive } from "@/lib/task-ui";
import { type TweetRecord } from "@/lib/task-results";

const FailedRepliesPanel = dynamic(
    () => import("@/components/features/FailedRepliesPanel").then((module) => ({ default: module.FailedRepliesPanel })),
    {
        loading: () => <PanelSkeleton title="失败评论记录" />,
    },
);

const TaskResultsSectionLazy = dynamic(
    () => import("@/components/features/task-detail/TaskResultsSection").then((module) => ({ default: module.TaskResultsSection })),
    {
        loading: () => <PanelSkeleton title="任务结果" />,
    },
);

export default function TaskResultPage() {
    const { id } = useParams() as { id: string };
    const router = useRouter();
    const { push } = useToast();
    const [liveControlState, setLiveControlState] = React.useState<"pause" | "resume" | "stop" | null>(null);
    const [backfilling, setBackfilling] = React.useState(false);
    const { stream, task, isLoading, refetch, latestActionEvent } = useTaskLiveData(id, liveControlState);
    const { exporting, controlling, confirmStop, setConfirmStop, handleExport, handleControl } = useTaskControls(
        task,
        refetch,
        setLiveControlState,
    );

    const finishedTweets = React.useMemo(() => ((task?.tweets ?? []) as TweetRecord[]), [task]);
    const resultState = useTaskResultState(finishedTweets, task?.task_id);

    const copyText = React.useCallback(async (label: string, value: string) => {
        if (typeof navigator === "undefined" || !navigator.clipboard) {
            push({ type: "error", title: "当前环境不支持复制" });
            return;
        }

        try {
            await navigator.clipboard.writeText(value);
            push({ type: "success", title: `已复制${label}` });
        } catch (err) {
            console.error("复制失败:", err);
            push({ type: "error", title: `复制${label}失败` });
        }
    }, [push]);

    const scrollToResults = React.useCallback(() => {
        const element = document.getElementById("task-results");
        if (!element) return;
        element.scrollIntoView({ behavior: "smooth", block: "start" });
    }, []);

    const handleCreateCommentBackfill = React.useCallback(async () => {
        if (!task) return;
        setBackfilling(true);
        try {
            const result = await api.commentBackfill.fromTasks({
                taskIds: [task.task_id],
                replyDepth: 2,
                maxRepliesPerTweet: 0,
            });
            const created = result.tasks[0];
            if (!created) {
                throw new Error("评论补采任务创建失败");
            }
            push({
                type: "success",
                title: "评论补采任务已创建",
                description: "默认已开启二级评论补采，正在跳转新任务详情。",
            });
            router.push(`/tasks/${created.task_id}`);
        } catch (err) {
            console.error(err);
            push({
                type: "error",
                title: "创建评论补采任务失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setBackfilling(false);
        }
    }, [push, router, task]);

    if (isLoading && !task) {
        return (
            <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="font-medium text-muted-foreground">正在加载任务详情...</p>
            </div>
        );
    }

    if (!task) {
        return (
            <EmptyState
                icon={Database}
                title="未找到采集记录"
                description="该任务可能已被清理、删除，或当前地址无效。"
                action={
                    <Link href="/tasks">
                        <Button variant="outline" className="rounded-xl">返回采集队列</Button>
                    </Link>
                }
            />
        );
    }

    const isRunning = task.status === "running" || task.status === "pending";
    const isPaused = task.status === "paused";
    const isRiskPaused = isPaused && task.risk_state !== "none";
    const active = isTaskActive(task.status);
    const exportReady = task.result_count > 0;
    const canBackfill = canCreateCommentBackfillFromTask(task);

    return (
        <div className="mx-auto max-w-6xl space-y-6 pb-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
            <TaskDetailHeader
                task={task}
                active={active}
                isRunning={isRunning}
                isPaused={isPaused}
                exportReady={exportReady}
                canBackfill={canBackfill}
                backfilling={backfilling}
                connected={stream.connected}
                lastMessageAt={stream.lastMessageAt}
                controlling={controlling}
                exporting={exporting}
                onCopyTaskId={() => void copyText("任务 ID", task.task_id)}
                onCopyKeyword={() => void copyText("关键词", task.keyword)}
                onScrollResults={scrollToResults}
                onBackfill={() => void handleCreateCommentBackfill()}
                onPause={() => void handleControl("pause")}
                onResume={() => void handleControl("resume")}
                onStop={() => setConfirmStop(true)}
                onExport={(format) => void handleExport(format)}
            />

            <TaskDetailOverview
                task={task}
                active={active}
                isRiskPaused={isRiskPaused}
                latestActionEvent={latestActionEvent}
                streamConnected={stream.connected}
                streamEvents={stream.events}
            />

            {task.fetch_replies ? <FailedRepliesPanel taskId={task.task_id} taskStatus={task.status} /> : null}

            <TaskResultsSectionLazy
                task={task}
                active={active}
                exportReady={exportReady}
                finishedTweets={finishedTweets}
                filteredFinishedTweets={resultState.filteredFinishedTweets}
                paginatedFinishedTweets={resultState.paginatedFinishedTweets}
                resultStats={resultState.resultStats}
                resultQuery={resultState.resultQuery}
                onResultQueryChange={resultState.setResultQuery}
                resultFilter={resultState.resultFilter}
                onResultFilterChange={resultState.setResultFilter}
                resultSort={resultState.resultSort}
                onResultSortChange={resultState.setResultSort}
                resultPageSize={resultState.resultPageSize}
                onResultPageSizeChange={resultState.setResultPageSize}
                resultDensity={resultState.resultDensity}
                onResultDensityChange={resultState.setResultDensity}
                visibleResultPage={resultState.visibleResultPage}
                totalResultPages={resultState.totalResultPages}
                resultPageInput={resultState.resultPageInput}
                onResultPageInputChange={resultState.setResultPageInput}
                onGoToResultPage={resultState.goToResultPage}
                onResetFilters={resultState.resetResultFilters}
            />

            <ConfirmDialog
                open={confirmStop}
                title="确认终止该任务？"
                description="已抓取的数据会保留，任务状态将变为已终止。"
                confirmText="终止任务"
                cancelText="取消"
                onCancel={() => setConfirmStop(false)}
                onConfirm={async () => {
                    setConfirmStop(false);
                    await handleControl("stop");
                }}
            />
        </div>
    );
}

function PanelSkeleton({ title }: { title: string }) {
    return (
        <div className="rounded-[1.5rem] border border-border/60 bg-card/90 p-5 shadow-sm">
            <div className="space-y-3 animate-pulse">
                <div className="h-5 w-32 rounded bg-muted" />
                <div className="h-4 w-2/3 rounded bg-muted" />
                <div className="grid gap-3 md:grid-cols-3">
                    <div className="h-20 rounded-xl bg-muted/80" />
                    <div className="h-20 rounded-xl bg-muted/80" />
                    <div className="h-20 rounded-xl bg-muted/80" />
                </div>
                <p className="text-xs text-muted-foreground">正在加载{title}...</p>
            </div>
        </div>
    );
}
