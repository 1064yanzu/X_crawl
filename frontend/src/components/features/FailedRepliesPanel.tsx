"use client";
import * as React from "react";
import {
    AlertTriangle, RotateCcw, FileDown, Loader2, CheckCircle2,
    ExternalLink, Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, FailedReplyRecord, FailedRepliesResponse } from "@/services/api";

interface FailedRepliesPanelProps {
    taskId: string;
    taskStatus: string;
}

export function FailedRepliesPanel({ taskId, taskStatus }: FailedRepliesPanelProps) {
    const [data, setData] = React.useState<FailedRepliesResponse | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [retrying, setRetrying] = React.useState(false);
    const [retryResult, setRetryResult] = React.useState<string | null>(null);

    const fetchData = React.useCallback(async () => {
        try {
            const resp = await api.failedReplies.list(taskId);
            setData(resp);
        } catch {
            setData(null);
        } finally {
            setLoading(false);
        }
    }, [taskId]);

    React.useEffect(() => {
        fetchData();
    }, [fetchData]);

    // 重试后自动刷新
    React.useEffect(() => {
        if (retryResult) {
            const timer = setTimeout(() => {
                fetchData();
                setRetryResult(null);
            }, 3000);
            return () => clearTimeout(timer);
        }
    }, [retryResult, fetchData]);

    const handleRetry = async () => {
        setRetrying(true);
        setRetryResult(null);
        try {
            const resp = await api.failedReplies.retry(taskId);
            setRetryResult(resp.message);
            // 3 秒后自动刷新列表
            setTimeout(() => fetchData(), 3000);
        } catch (err) {
            setRetryResult(`重试失败：${err instanceof Error ? err.message : String(err)}`);
        } finally {
            setRetrying(false);
        }
    };

    const handleExport = async () => {
        try {
            await api.failedReplies.exportCsv(taskId);
        } catch (err) {
            setRetryResult(`导出失败：${err instanceof Error ? err.message : String(err)}`);
        }
    };

    // 无数据 or 加载中
    if (loading) return null;
    if (!data || data.stats.total === 0) return null;

    const pendingCount = data.stats.pending;
    const resolvedCount = data.stats.resolved;
    const isTaskDone = taskStatus === "done" || taskStatus === "stopped" || taskStatus === "failed";

    return (
        <div className="bg-amber-50/50 dark:bg-amber-950/10 border border-amber-200 dark:border-amber-900/40 rounded-xl p-5 space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0" />
                    <div>
                        <h4 className="font-semibold text-amber-800 dark:text-amber-300 text-sm">
                            评论抓取不完整
                        </h4>
                        <p className="text-xs text-amber-700/80 dark:text-amber-400/70 mt-0.5">
                            共 {data.stats.total} 条帖子的评论抓取失败或不完整
                            {resolvedCount > 0 && `，其中 ${resolvedCount} 条已通过重试解决`}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    {pendingCount > 0 && isTaskDone && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleRetry}
                            disabled={retrying}
                            className="h-8 text-xs border-amber-300 text-amber-700 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-400 dark:hover:bg-amber-900/30"
                        >
                            {retrying ? (
                                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                            ) : (
                                <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                            )}
                            重试全部 ({pendingCount})
                        </Button>
                    )}
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleExport}
                        className="h-8 text-xs text-amber-700 hover:bg-amber-100 dark:text-amber-400 dark:hover:bg-amber-900/30"
                    >
                        <FileDown className="w-3.5 h-3.5 mr-1.5" />
                        导出
                    </Button>
                </div>
            </div>

            {/* 重试结果提示 */}
            {retryResult && (
                <div className="bg-white/60 dark:bg-black/10 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2 text-xs text-amber-700 dark:text-amber-300 animate-in fade-in">
                    {retryResult}
                </div>
            )}

            {/* 统计 */}
            <div className="grid grid-cols-3 gap-3">
                <div className="bg-white/50 dark:bg-black/10 rounded-lg px-3 py-2.5 border border-amber-100 dark:border-amber-900/30">
                    <p className="text-[10px] text-amber-600/70 dark:text-amber-400/50 uppercase tracking-wider">待重试</p>
                    <p className="text-lg font-bold text-amber-700 dark:text-amber-300 font-mono">{pendingCount}</p>
                </div>
                <div className="bg-white/50 dark:bg-black/10 rounded-lg px-3 py-2.5 border border-amber-100 dark:border-amber-900/30">
                    <p className="text-[10px] text-amber-600/70 dark:text-amber-400/50 uppercase tracking-wider">重试中</p>
                    <p className="text-lg font-bold text-amber-700 dark:text-amber-300 font-mono">{data.stats.retrying}</p>
                </div>
                <div className="bg-white/50 dark:bg-black/10 rounded-lg px-3 py-2.5 border border-green-100 dark:border-green-900/30">
                    <p className="text-[10px] text-green-600/70 dark:text-green-400/50 uppercase tracking-wider">已解决</p>
                    <p className="text-lg font-bold text-green-600 dark:text-green-400 font-mono">{resolvedCount}</p>
                </div>
            </div>

            {/* 记录列表 */}
            <div className="max-h-64 overflow-y-auto space-y-0 rounded-lg border border-amber-100 dark:border-amber-900/30 divide-y divide-amber-100 dark:divide-amber-900/30 bg-white/40 dark:bg-black/10">
                {data.records.map((rec: FailedReplyRecord) => (
                    <div
                        key={`${rec.tweet_id}-${rec.id}`}
                        className="px-3 py-2.5 text-xs flex items-center gap-3 hover:bg-amber-50/50 dark:hover:bg-amber-950/20 transition-colors"
                    >
                        {/* Status icon */}
                        <div className="shrink-0">
                            {rec.status === "resolved" ? (
                                <CheckCircle2 className="w-4 h-4 text-green-500" />
                            ) : rec.status === "retrying" ? (
                                <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />
                            ) : (
                                <AlertTriangle className="w-4 h-4 text-amber-500" />
                            )}
                        </div>

                        {/* Info */}
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                                <a
                                    href={`https://x.com/${rec.screen_name}/status/${rec.tweet_id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="font-mono text-foreground/80 hover:text-primary hover:underline truncate flex items-center gap-1"
                                >
                                    @{rec.screen_name}
                                    <ExternalLink className="w-3 h-3 shrink-0" />
                                </a>
                                <StatusBadge status={rec.status} />
                            </div>
                            <p className="text-muted-foreground truncate">{rec.error_reason}</p>
                        </div>

                        {/* Counts */}
                        <div className="text-right shrink-0">
                            <span className="font-mono">
                                {rec.fetched_count}
                                <span className="text-muted-foreground"> / {rec.expected_count}</span>
                            </span>
                        </div>

                        {/* Time */}
                        <div className="text-muted-foreground shrink-0 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            <span className="truncate max-w-[80px]">
                                {rec.retried_at
                                    ? new Date(rec.retried_at).toLocaleTimeString()
                                    : new Date(rec.created_at).toLocaleTimeString()}
                            </span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function StatusBadge({ status }: { status: string }) {
    switch (status) {
        case "resolved":
            return <Badge className="bg-green-500/10 text-green-600 border-0 text-[10px] px-1.5 py-0">已解决</Badge>;
        case "retrying":
            return <Badge className="bg-blue-500/10 text-blue-600 border-0 text-[10px] px-1.5 py-0">重试中</Badge>;
        default:
            return <Badge className="bg-amber-500/10 text-amber-600 border-0 text-[10px] px-1.5 py-0">待重试</Badge>;
    }
}
