"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, CheckpointInfo } from "@/services/api";
import { Bookmark, Trash2, Play, Search, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

export default function CheckpointsPage() {
    const router = useRouter();
    const { push } = useToast();
    const [checkpoints, setCheckpoints] = React.useState<CheckpointInfo[]>([]);
    const [loading, setLoading] = React.useState(true);
    const [resuming, setResuming] = React.useState<string | null>(null);
    const [deleteId, setDeleteId] = React.useState<string | null>(null);

    React.useEffect(() => {
        fetchCheckpoints();
    }, []);

    const fetchCheckpoints = async () => {
        try {
            const data = await api.checkpoints.list();
            setCheckpoints(data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (taskId: string) => {
        try {
            await api.checkpoints.delete(taskId);
            setCheckpoints(checkpoints.filter((c) => c.task_id !== taskId));
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
            // Calling search create with same criteria + task_id + resume=true
            const task = await api.search.create({
                keyword: checkpoint.keyword,
                max_count: 0, // 断点恢复不限制采集量（0 表示无上限）
                product: checkpoint.product as "Top" | "Latest" | "Photos" | "Videos",
                resume: true,
                task_id: checkpoint.task_id
            });
            push({ type: "success", title: "已提交恢复任务" });
            router.push(`/tasks/${task.task_id}`);
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "恢复断点失败", description: "数据可能已损坏或失效" });
        } finally {
            setResuming(null);
        }
    };

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight mb-2">断点任务</h2>
                    <p className="text-muted-foreground">管理并恢复已暂停或意外中断的采集任务。</p>
                </div>
            </div>

            {loading ? (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {[1, 2, 3].map(i => <div key={i} className="h-40 bg-card border rounded-xl animate-pulse" />)}
                </div>
            ) : checkpoints.length === 0 ? (
                <Card className="flex flex-col items-center justify-center py-20 text-center border-dashed">
                    <Bookmark className="w-10 h-10 text-muted-foreground/30 mb-4" />
                    <h3 className="text-lg font-medium">暂无断点任务</h3>
                    <p className="text-sm text-muted-foreground max-w-sm mt-1 mb-6">
                        开启了断点续传功能的中断任务将在此处显示。
                    </p>
                    <Link href="/">
                        <Button variant="outline"><Search className="w-4 h-4 mr-2" /> 发起支持断点续传的任务</Button>
                    </Link>
                </Card>
            ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {checkpoints.map((cp) => (
                        <Card key={cp.task_id} className="flex flex-col">
                            <CardHeader className="p-4 sm:p-5 pb-3">
                                <CardTitle className="flex items-center justify-between text-lg">
                                    <span className="truncate pr-2">{cp.keyword}</span>
                                    {cp.can_resume ? (
                                        <Badge variant="success" className="shrink-0 bg-green-500/15 text-green-700">可恢复</Badge>
                                    ) : (
                                        <Badge variant="destructive" className="shrink-0 text-[10px] px-1.5"><AlertCircle className="w-3 h-3 mr-1" /> 已结束</Badge>
                                    )}
                                </CardTitle>
                                <CardDescription className="text-xs font-mono truncate">{cp.task_id}</CardDescription>
                            </CardHeader>

                            <CardContent className="p-4 sm:p-5 pt-0 flex-1 flex flex-col justify-between">
                                <div className="grid grid-cols-2 gap-y-3 mb-6 text-sm">
                                    <div>
                                        <span className="text-muted-foreground block text-xs">检索类型</span>
                                        <span className="font-medium bg-secondary px-1.5 py-0.5 rounded text-xs">{cp.product}</span>
                                    </div>
                                    <div>
                                        <span className="text-muted-foreground block text-xs">保存时间</span>
                                        <span className="font-medium text-[11px]">{new Date(cp.saved_at).toLocaleString()}</span>
                                    </div>
                                    <div>
                                        <span className="text-muted-foreground block text-xs">已采集推文</span>
                                        <span className="font-medium">{cp.tweets_count}</span>
                                    </div>
                                    <div>
                                        <span className="text-muted-foreground block text-xs">已采集页数</span>
                                        <span className="font-medium">{cp.page_fetched}</span>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2 pt-4 border-t mt-auto">
                                    <Button
                                        className="flex-1 text-xs"
                                        disabled={!cp.can_resume || resuming === cp.task_id}
                                        isLoading={resuming === cp.task_id}
                                        onClick={() => handleResume(cp)}
                                    >
                                        <Play className="w-3.5 h-3.5 mr-1" /> 恢复任务
                                    </Button>
                                    <Button
                                        variant="outline"
                                        size="icon"
                                        className="text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20 shrink-0"
                                        onClick={() => setDeleteId(cp.task_id)}
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </Button>
                                </div>
                            </CardContent>
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
