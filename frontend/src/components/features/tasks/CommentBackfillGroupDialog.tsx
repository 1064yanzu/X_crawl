"use client";

import * as React from "react";
import { Layers, Loader2, X, AlertTriangle, CheckCircle2, MessageCircleMore, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/services/api";
import type { TaskOut } from "@/services/api";
import { cn } from "@/lib/utils";

export function CommentBackfillGroupDialog({
    open,
    tasks,
    onClose,
    onSuccess,
    onError,
}: {
    open: boolean;
    tasks: TaskOut[];
    onClose: () => void;
    onSuccess: (groupTaskId: string, message: string) => void;
    onError: (message: string) => void;
}) {
    const [replyDepth, setReplyDepth] = React.useState(2);
    const [groupName, setGroupName] = React.useState("");
    const [concurrency, setConcurrency] = React.useState(1);
    const [submitting, setSubmitting] = React.useState(false);

    // 重置表单状态
    React.useEffect(() => {
        if (open) {
            setReplyDepth(2);
            setGroupName("");
            setConcurrency(1);
            setSubmitting(false);
        }
    }, [open]);

    const sourceTaskIds = tasks.map((t) => t.task_id);

    // 统计整体待采数（已处理的跳过）
    const totalExpectedPosts = tasks.reduce((acc, t) => {
        const progress = t.comment_backfill_progress;
        if (progress) {
            return acc + Math.max(0, progress.total_posts - progress.processed_posts);
        }
        return acc + t.result_count;
    }, 0);

    const handleSubmit = async () => {
        if (sourceTaskIds.length === 0) return;
        setSubmitting(true);
        try {
            const res = await api.commentBackfill.createGroup({
                sourceTaskIds,
                replyDepth,
                maxRepliesPerTweet: 0, // 始终无限制，不对外暴露此参数
                groupName: groupName.trim() || undefined,
                concurrency,
            });
            const incl = res.sources.filter((s) => s.status === "included").length;
            onSuccess(
                res.group_task_id,
                `任务组已创建：合并 ${incl} 个源任务，共 ${res.total_posts} 条帖子，正在启动...`,
            );
            onClose();
        } catch (err) {
            onError(err instanceof Error ? err.message : String(err));
        } finally {
            setSubmitting(false);
        }
    };

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/40 p-4">
            <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border bg-card shadow-xl">
                {/* ── 标题栏 ── */}
                <div className="flex shrink-0 items-center justify-between border-b px-6 py-4">
                    <div className="flex items-center gap-2.5">
                        <div className="rounded-full bg-violet-500/10 p-2 text-violet-600 dark:text-violet-400">
                            <Layers className="h-4 w-4" />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold">合并为评论补采任务组</h3>
                            <p className="text-sm text-muted-foreground">
                                将 {tasks.length} 个补采任务的帖子合并，以最高效率统一抓取
                            </p>
                        </div>
                    </div>
                    <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-lg"
                        onClick={onClose}
                        disabled={submitting}
                    >
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                {/* ── 内容 ── */}
                <div className="flex-1 overflow-y-auto px-6 py-4">
                    {/* 工作原理说明 */}
                    <div className="mb-4 rounded-xl border border-violet-500/20 bg-violet-500/5 p-4">
                        <div className="flex items-start gap-2 text-sm text-violet-800 dark:text-violet-300">
                            <MessageCircleMore className="mt-0.5 h-4 w-4 shrink-0" />
                            <div className="space-y-1 leading-relaxed">
                                <p className="font-medium">任务组的核心优势</p>
                                <ul className="list-disc space-y-1 pl-4 text-xs opacity-90">
                                    <li>支持多路并发：每路使用独立账号 + 独立浏览器，吞吐量倍增</li>
                                    <li>一级评论（L1）与二级评论（L2）分别使用独立 Chrome 进程，零资源竞争</li>
                                    <li>帖子按评论数降序排列，高价值帖子优先处理</li>
                                    <li>全局去重：来自多个源任务的相同帖子只补采一次</li>
                                </ul>
                            </div>
                        </div>
                    </div>

                    {/* 源任务列表 */}
                    <div className="mb-4">
                        <h4 className="mb-2 text-sm font-medium">
                            源任务（{tasks.length} 个）
                            <span className="ml-2 text-xs font-normal text-muted-foreground">
                                合并后约 {totalExpectedPosts} 条帖子待补采
                            </span>
                        </h4>
                        <div className="overflow-hidden rounded-xl border">
                            <ul className="divide-y text-sm">
                                {tasks.map((task) => {
                                    const progress = task.comment_backfill_progress;
                                    const total = progress?.total_posts ?? task.result_count;
                                    const processed = progress?.processed_posts ?? 0;
                                    const remaining = Math.max(0, total - processed);
                                    const hasProgress = progress != null && total > 0;
                                    const pct = hasProgress ? Math.round((processed / total) * 100) : 0;
                                    const isFullyDone = hasProgress && remaining === 0;

                                    return (
                                        <li
                                            key={task.task_id}
                                            className={cn(
                                                "px-4 py-3",
                                                isFullyDone && "opacity-50",
                                            )}
                                        >
                                            <div className="flex items-start gap-3">
                                                {/* 状态图标 */}
                                                <div className="mt-0.5 shrink-0">
                                                    {isFullyDone ? (
                                                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                                                    ) : (
                                                        <div className="h-1.5 w-1.5 translate-y-1 rounded-full bg-primary" />
                                                    )}
                                                </div>

                                                {/* 关键词 + ID */}
                                                <div className="min-w-0 flex-1">
                                                    <p className="truncate text-xs font-medium leading-snug">
                                                        {task.keyword}
                                                    </p>
                                                    <p className="text-[11px] text-muted-foreground">
                                                        {task.task_id.slice(0, 8)} · {task.status}
                                                    </p>

                                                    {/* 进度条（仅在有进度数据时显示） */}
                                                    {hasProgress && (
                                                        <div className="mt-1.5">
                                                            <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                                                                <div
                                                                    className={cn(
                                                                        "h-full rounded-full transition-all",
                                                                        isFullyDone
                                                                            ? "bg-emerald-500"
                                                                            : "bg-violet-500",
                                                                    )}
                                                                    style={{ width: `${pct}%` }}
                                                                />
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>

                                                {/* 已采 / 待采 数字 */}
                                                <div className="shrink-0 text-right">
                                                    {hasProgress ? (
                                                        <>
                                                            {processed > 0 && (
                                                                <p className="text-[11px] text-emerald-600 dark:text-emerald-400">
                                                                    已采 {processed} 条
                                                                </p>
                                                            )}
                                                            <p className={cn(
                                                                "tabular-nums text-xs font-medium",
                                                                isFullyDone
                                                                    ? "text-muted-foreground"
                                                                    : "text-foreground",
                                                            )}>
                                                                {isFullyDone ? "已全部采集" : `待采 ${remaining} 条`}
                                                            </p>
                                                            <p className="text-[10px] text-muted-foreground">
                                                                共 {total} 条
                                                            </p>
                                                        </>
                                                    ) : (
                                                        <span className="tabular-nums text-xs font-medium">
                                                            {total} 条
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        </div>
                    </div>

                    {/* 配置 */}
                    <div className="space-y-3">
                        <div>
                            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                                评论深度
                            </label>
                            <select
                                className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                                value={replyDepth}
                                onChange={(e) => setReplyDepth(Number(e.target.value))}
                                disabled={submitting}
                            >
                                <option value={1}>1 级（仅一级评论）</option>
                                <option value={2}>2 级（含二级评论，推荐）</option>
                                <option value={3}>3 级</option>
                            </select>
                        </div>
                        <div>
                            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                                <Zap className="h-3 w-3" />
                                并发数
                            </label>
                            <div className="flex items-center gap-2">
                                {[1, 2, 3, 4, 5].map((n) => (
                                    <button
                                        key={n}
                                        type="button"
                                        className={cn(
                                            "flex h-9 w-12 items-center justify-center rounded-lg border text-sm font-medium transition-colors",
                                            concurrency === n
                                                ? "border-violet-500 bg-violet-500/10 text-violet-700 dark:text-violet-300"
                                                : "border-border bg-background text-muted-foreground hover:border-violet-500/50 hover:text-foreground",
                                        )}
                                        onClick={() => setConcurrency(n)}
                                        disabled={submitting}
                                    >
                                        {n}
                                    </button>
                                ))}
                            </div>
                            <p className="mt-1.5 text-[11px] text-muted-foreground">
                                {concurrency === 1
                                    ? "单路模式：使用 1 个账号 + 1 组浏览器"
                                    : `${concurrency} 路并发：使用 ${concurrency} 个账号 + ${concurrency} 组独立浏览器，吞吐量提升约 ${concurrency}x`}
                                <br />
                                实际并发数受可用账号数限制，不足时自动降级
                            </p>
                        </div>
                        <div>
                            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                                任务组名称（可选，留空自动生成）
                            </label>
                            <Input
                                placeholder="例：热点话题评论补采组"
                                value={groupName}
                                onChange={(e) => setGroupName(e.target.value)}
                                disabled={submitting}
                                className="rounded-lg text-sm"
                            />
                        </div>
                    </div>

                    {tasks.length < 2 && (
                        <div className="mt-4 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-700 dark:text-amber-400">
                            <AlertTriangle className="h-4 w-4 shrink-0" />
                            <span>请至少选择 2 个评论补采任务来创建任务组</span>
                        </div>
                    )}
                </div>

                {/* ── 底部操作 ── */}
                <div className="flex shrink-0 items-center justify-end gap-2 border-t px-6 py-4">
                    <Button
                        variant="outline"
                        size="sm"
                        className="rounded-xl"
                        onClick={onClose}
                        disabled={submitting}
                    >
                        取消
                    </Button>
                    <Button
                        size="sm"
                        className="rounded-xl bg-violet-600 text-white hover:bg-violet-700"
                        onClick={() => void handleSubmit()}
                        disabled={submitting || tasks.length < 1}
                    >
                        {submitting ? (
                            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        ) : (
                            <Layers className="mr-1.5 h-3.5 w-3.5" />
                        )}
                        {submitting ? "创建中..." : `创建任务组（${tasks.length} 个源任务）`}
                    </Button>
                </div>
            </div>
        </div>
    );
}
