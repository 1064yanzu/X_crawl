"use client";

import * as React from "react";
import { Loader2, MessageCircleMore, Settings2, Slash, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/services/api";
import type { ReplyCollectionMode, TaskOut } from "@/services/api";
import { canBatchUpdateReplyCollection, isTaskWithReplyCollection } from "@/lib/task-ui";

function getModeLabel(mode: ReplyCollectionMode) {
    return mode === "with_comments" ? "采集评论" : "不采集评论";
}

function getTaskModeLabel(task: Pick<TaskOut, "platform" | "fetch_replies" | "reply_depth">) {
    const withComments = isTaskWithReplyCollection(task);
    if (!withComments) return "不采评论";
    return (task.platform ?? "x") === "x" ? "采评论（二级）" : "采评论";
}

export function BatchReplyCollectionDialog({
    open,
    tasks,
    onClose,
    onSuccess,
    onError,
}: {
    open: boolean;
    tasks: TaskOut[];
    onClose: () => void;
    onSuccess: (message: string) => void;
    onError: (message: string) => void;
}) {
    const [submittingMode, setSubmittingMode] = React.useState<ReplyCollectionMode | null>(null);

    const eligibleTasks = React.useMemo(
        () => tasks.filter((task) => canBatchUpdateReplyCollection(task)),
        [tasks],
    );
    const withCommentsTasks = React.useMemo(
        () => eligibleTasks.filter((task) => isTaskWithReplyCollection(task)),
        [eligibleTasks],
    );
    const withoutCommentsTasks = React.useMemo(
        () => eligibleTasks.filter((task) => !isTaskWithReplyCollection(task)),
        [eligibleTasks],
    );
    const ineligibleCount = tasks.length - eligibleTasks.length;
    const xEligibleCount = React.useMemo(
        () => eligibleTasks.filter((task) => (task.platform ?? "x") === "x").length,
        [eligibleTasks],
    );
    const weiboEligibleCount = eligibleTasks.length - xEligibleCount;

    const handleSubmit = async (mode: ReplyCollectionMode) => {
        if (eligibleTasks.length === 0) return;
        setSubmittingMode(mode);
        try {
            const result = await api.tasks.batchUpdateReplyCollection(
                tasks.map((task) => task.task_id),
                mode,
            );
            onSuccess(result.message);
            onClose();
        } catch (err) {
            onError(err instanceof Error ? err.message : String(err));
        } finally {
            setSubmittingMode(null);
        }
    };

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/40 p-4">
            <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-md border bg-card p-6 shadow-xl">
                <div className="mb-4 flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                        <div className="rounded-full bg-primary/10 p-2 text-primary">
                            <Settings2 className="h-4 w-4" />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold">批量修改采评模式</h3>
                            <p className="text-sm text-muted-foreground">
                                已选择 {tasks.length} 个任务，符合条件 {eligibleTasks.length} 个
                            </p>
                        </div>
                    </div>
                    <Button variant="ghost" size="sm" className="rounded-lg" onClick={onClose} disabled={submittingMode !== null}>
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                <div className="mb-4 flex-1 space-y-4 overflow-y-auto">
                    <div className="rounded-md border border-border bg-muted/20 p-4 text-sm text-muted-foreground">
                        <p className="font-medium text-foreground">这次操作会把任务切成两种明确模式</p>
                        <ul className="mt-2 list-disc space-y-1 pl-5">
                            <li><span className="text-foreground">采集评论</span>：开启评论采集；其中 X 任务会统一按二级评论模式执行。</li>
                            <li><span className="text-foreground">不采集评论</span>：关闭评论采集，仅保留帖子采集。</li>
                            <li>当前支持 <span className="text-foreground">X / 微博 的帖子采集任务</span>，且任务状态需为已完成 / 已停止 / 已失败。</li>
                        </ul>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-3">
                        <div className="rounded-md border bg-card p-4">
                            <p className="text-xs text-muted-foreground">可改为采评论</p>
                            <p className="mt-2 text-2xl font-semibold tabular-nums">{withoutCommentsTasks.length}</p>
                        </div>
                        <div className="rounded-md border bg-card p-4">
                            <p className="text-xs text-muted-foreground">可改为不采评论</p>
                            <p className="mt-2 text-2xl font-semibold tabular-nums">{withCommentsTasks.length}</p>
                        </div>
                        <div className="rounded-md border bg-card p-4">
                            <p className="text-xs text-muted-foreground">符合条件平台</p>
                            <p className="mt-2 text-sm font-semibold text-foreground">X {xEligibleCount} · 微博 {weiboEligibleCount}</p>
                        </div>
                        <div className="rounded-md border bg-card p-4 sm:col-span-3">
                            <p className="text-xs text-muted-foreground">不符合条件</p>
                            <p className="mt-2 text-2xl font-semibold tabular-nums">{ineligibleCount}</p>
                        </div>
                    </div>

                    {eligibleTasks.length > 0 ? (
                        <div className="space-y-3">
                            <h4 className="text-sm font-medium">本次将处理的任务</h4>
                            <div className="overflow-hidden rounded-md border">
                                <ul className="divide-y text-sm">
                                    {eligibleTasks.map((task) => {
                                        const withComments = isTaskWithReplyCollection(task);
                                        return (
                                            <li key={task.task_id} className="flex items-center gap-3 px-4 py-3">
                                                {withComments ? (
                                                    <MessageCircleMore className="h-4 w-4 shrink-0 text-primary" />
                                                ) : (
                                                    <Slash className="h-4 w-4 shrink-0 text-muted-foreground" />
                                                )}
                                                <div className="min-w-0 flex-1">
                                                    <p className="truncate font-medium text-foreground">{task.keyword}</p>
                                                    <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                                                        <code>{task.task_id.slice(0, 8)}</code>
                                                        <span>{(task.platform ?? "x") === "x" ? "X" : "微博"}</span>
                                                        <span>{task.status}</span>
                                                        <span>当前：{getTaskModeLabel(task)}</span>
                                                    </div>
                                                </div>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </div>
                        </div>
                    ) : (
                        <div className="rounded-md border border-dashed border-border bg-muted/20 p-6 text-center text-sm text-muted-foreground">
                            当前选中的任务里，没有符合条件的 X / 微博历史帖子采集任务。
                        </div>
                    )}
                </div>

                <div className="mt-auto flex flex-wrap items-center justify-end gap-2 border-t pt-4">
                    <Button variant="outline" size="sm" className="rounded-md" onClick={onClose} disabled={submittingMode !== null}>
                        取消
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        className="rounded-md"
                        onClick={() => void handleSubmit("without_comments")}
                        disabled={submittingMode !== null || withCommentsTasks.length === 0}
                    >
                        {submittingMode === "without_comments" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Slash className="mr-1.5 h-3.5 w-3.5" />}
                        改为{getModeLabel("without_comments")}
                    </Button>
                    <Button
                        size="sm"
                        className="rounded-md bg-primary text-primary-foreground hover:bg-primary/90"
                        onClick={() => void handleSubmit("with_comments")}
                        disabled={submittingMode !== null || withoutCommentsTasks.length === 0}
                    >
                        {submittingMode === "with_comments" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <MessageCircleMore className="mr-1.5 h-3.5 w-3.5" />}
                        改为{getModeLabel("with_comments")}
                    </Button>
                </div>
            </div>
        </div>
    );
}
