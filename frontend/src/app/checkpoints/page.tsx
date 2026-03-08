"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, Bookmark, Play, Search, Trash2 } from "lucide-react";
import { api, CheckpointInfo } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageHeader } from "@/components/ui/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";

export default function CheckpointsPage() {
    const router = useRouter();
    const { push } = useToast();
    const [checkpoints, setCheckpoints] = React.useState<CheckpointInfo[]>([]);
    const [loading, setLoading] = React.useState(true);
    const [resuming, setResuming] = React.useState<string | null>(null);
    const [deleteId, setDeleteId] = React.useState<string | null>(null);

    const fetchCheckpoints = React.useCallback(async () => {
        try {
            const data = await api.checkpoints.list();
            setCheckpoints(data);
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "加载断点失败" });
        } finally {
            setLoading(false);
        }
    }, [push]);

    React.useEffect(() => {
        void fetchCheckpoints();
    }, [fetchCheckpoints]);

    const handleDelete = async (taskId: string) => {
        try {
            await api.checkpoints.delete(taskId);
            setCheckpoints((prev) => prev.filter((checkpoint) => checkpoint.task_id !== taskId));
            push({ type: "success", title: "断点已删除" });
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "删除断点失败" });
        }
    };

    const handleResume = async (checkpoint: CheckpointInfo) => {
        if (!checkpoint.can_resume) return;
        setResuming(checkpoint.task_id);
        try {
            const task = await api.search.create({
                keyword: checkpoint.keyword,
                max_count: 0,
                product: checkpoint.product as "Top" | "Latest" | "Photos" | "Videos",
                resume: true,
                task_id: checkpoint.task_id,
            });
            push({ type: "success", title: "已提交恢复任务" });
            router.push(`/tasks/${task.task_id}`);
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "恢复断点失败", description: "数据可能已损坏或失效。" });
        } finally {
            setResuming(null);
        }
    };

    const resumable = checkpoints.filter((checkpoint) => checkpoint.can_resume).length;

    return (
        <div className="mx-auto max-w-6xl space-y-6 pb-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
            <PageHeader
                eyebrow="Resume Center"
                icon={Bookmark}
                title="断点任务"
                description="查看和恢复断点任务。"
            >
                <div className="grid gap-3 md:grid-cols-3">
                    <StatCard label="全部断点" value={checkpoints.length} hint="包含可恢复和已失效记录" icon={Bookmark} />
                    <StatCard label="可恢复" value={resumable} hint="可以直接继续抓取" icon={Play} tone="success" />
                    <StatCard label="待处理" value={Math.max(0, checkpoints.length - resumable)} hint="建议先检查是否还需要保留" icon={AlertCircle} tone="warning" />
                </div>
            </PageHeader>

            {loading ? (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {[1, 2, 3].map((item) => (
                        <div key={item} className="rounded-[1.5rem] border border-border/60 bg-card/80 p-5 shadow-sm">
                            <Skeleton className="h-6 w-1/2" />
                            <Skeleton className="mt-3 h-4 w-2/3" />
                            <div className="mt-4 grid gap-3 sm:grid-cols-2">
                                <Skeleton className="h-16 w-full" />
                                <Skeleton className="h-16 w-full" />
                            </div>
                            <Skeleton className="mt-4 h-10 w-full" />
                        </div>
                    ))}
                </div>
            ) : checkpoints.length === 0 ? (
                <EmptyState
                    icon={Bookmark}
                    title="暂无断点任务"
                    description="中断后保存的任务会显示在这里。"
                    action={
                        <Link href="/">
                            <Button variant="outline" className="rounded-xl">
                                <Search className="mr-2 h-4 w-4" />
                                去创建支持断点的任务
                            </Button>
                        </Link>
                    }
                />
            ) : (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {checkpoints.map((checkpoint) => (
                        <Card key={checkpoint.task_id} className="rounded-[1.5rem] border-border/60 bg-card/90 p-5 shadow-sm">
                            <div className="flex h-full flex-col gap-5">
                                <div className="space-y-3">
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="min-w-0">
                                            <h3 className="line-clamp-2 text-lg font-semibold text-foreground">{checkpoint.keyword}</h3>
                                            <p className="mt-1 truncate text-xs font-mono text-muted-foreground">{checkpoint.task_id}</p>
                                        </div>
                                        {checkpoint.can_resume ? (
                                            <Badge variant="success" className="rounded-full px-3 py-1">可恢复</Badge>
                                        ) : (
                                            <Badge variant="destructive" className="rounded-full px-3 py-1">已结束</Badge>
                                        )}
                                    </div>
                                    
                                </div>

                                <div className="grid gap-3 sm:grid-cols-2">
                                    <MetaBlock label="检索类型" value={checkpoint.product} />
                                    <MetaBlock label="保存时间" value={new Date(checkpoint.saved_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })} />
                                    <MetaBlock label="已采集推文" value={`${checkpoint.tweets_count}`} />
                                    <MetaBlock label="已采集页数" value={`${checkpoint.page_fetched}`} />
                                </div>

                                <div className="mt-auto flex items-center gap-2 border-t border-border/50 pt-4">
                                    <Button
                                        className="flex-1 rounded-xl"
                                        disabled={!checkpoint.can_resume || resuming === checkpoint.task_id}
                                        isLoading={resuming === checkpoint.task_id}
                                        onClick={() => void handleResume(checkpoint)}
                                    >
                                        <Play className="mr-1.5 h-3.5 w-3.5" />
                                        恢复任务
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="rounded-xl text-muted-foreground hover:text-red-600"
                                        onClick={() => setDeleteId(checkpoint.task_id)}
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>
                        </Card>
                    ))}
                </div>
            )}

            <ConfirmDialog
                open={Boolean(deleteId)}
                title="确定删除此断点吗？"
                description="删除后将无法从该断点恢复任务。"
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
        </div>
    );
}

function MetaBlock({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-3 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
            <p className="mt-1 text-sm font-medium text-foreground">{value}</p>
        </div>
    );
}
