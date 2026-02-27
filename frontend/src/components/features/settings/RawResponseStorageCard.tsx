"use client";
import * as React from "react";
import { DatabaseBackup, FileText, HardDrive, Loader2, Save, Trash2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, StorageInfo } from "@/services/api";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";

function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function RawResponseStorageCard() {
    const { push } = useToast();
    const [storage, setStorage] = React.useState<StorageInfo | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [saveEnabled, setSaveEnabled] = React.useState(true);
    const [maxPages, setMaxPages] = React.useState(0);
    const [savingConfig, setSavingConfig] = React.useState(false);
    const [deletingTaskId, setDeletingTaskId] = React.useState<string | null>(null);
    const [confirmDeleteTaskId, setConfirmDeleteTaskId] = React.useState<string | null>(null);
    const [confirmClearAll, setConfirmClearAll] = React.useState(false);
    const [clearingAll, setClearingAll] = React.useState(false);

    const refreshStorage = React.useCallback(async () => {
        const [storageInfo, crawlerConfig] = await Promise.all([
            api.rawResponses.list(),
            api.crawlerConfig.get(),
        ]);
        setStorage(storageInfo);
        setSaveEnabled(Boolean(crawlerConfig.save_raw_responses));
        setMaxPages(Math.max(0, Number(crawlerConfig.raw_responses_max_pages ?? 0)));
    }, []);

    React.useEffect(() => {
        refreshStorage()
            .catch(() => setStorage(null))
            .finally(() => setLoading(false));
    }, [refreshStorage]);

    const totalBytes = storage?.tasks.reduce((s, t) => s + t.total_bytes, 0) ?? 0;
    const totalPages = storage?.tasks.reduce((s, t) => s + t.page_count, 0) ?? 0;
    const isConfigDirty = saveEnabled !== Boolean(storage?.save_enabled)
        || maxPages !== Number(storage?.max_pages_per_task ?? 0);

    const handleSaveConfig = async () => {
        setSavingConfig(true);
        try {
            const current = await api.crawlerConfig.get();
            await api.crawlerConfig.update({
                ...current,
                save_raw_responses: saveEnabled,
                raw_responses_max_pages: Math.max(0, maxPages),
            });
            await refreshStorage();
            push({ type: "success", title: "原始响应配置已更新" });
        } catch (err) {
            push({
                type: "error",
                title: "保存失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setSavingConfig(false);
        }
    };

    const handleDeleteTask = async (taskId: string) => {
        setDeletingTaskId(taskId);
        try {
            await api.rawResponses.deleteTask(taskId);
            await refreshStorage();
            push({ type: "success", title: "任务归档已清理" });
        } catch (err) {
            push({
                type: "error",
                title: "清理失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setDeletingTaskId(null);
        }
    };

    const handleClearAll = async () => {
        setClearingAll(true);
        try {
            await api.rawResponses.deleteAll();
            await refreshStorage();
            push({ type: "success", title: "全部原始响应已清理" });
        } catch (err) {
            push({
                type: "error",
                title: "清理失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setClearingAll(false);
        }
    };

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2"><DatabaseBackup className="h-5 w-5 text-green-600" /> 原始响应存储</CardTitle>
                <CardDescription>搜索与回复原始 JSON 的本地归档信息。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {loading ? (
                    <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在读取存储信息...
                    </div>
                ) : storage ? (
                    <>
                        <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <p className="text-sm font-medium">保存原始响应</p>
                                    <p className="text-xs text-muted-foreground">关闭后不再写入新的 raw JSON。</p>
                                </div>
                                <input
                                    type="checkbox"
                                    checked={saveEnabled}
                                    onChange={(e) => setSaveEnabled(e.target.checked)}
                                />
                            </div>
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <p className="text-sm font-medium">每任务最大保存页数</p>
                                    <p className="text-xs text-muted-foreground">0 表示不限制。</p>
                                </div>
                                <input
                                    type="number"
                                    min={0}
                                    step={1}
                                    value={maxPages}
                                    onChange={(e) => setMaxPages(Math.max(0, Number(e.target.value) || 0))}
                                    className="h-8 w-28 rounded border bg-background px-2 text-sm"
                                />
                            </div>
                            <div className="flex justify-end">
                                <Button size="sm" onClick={handleSaveConfig} disabled={savingConfig || !isConfigDirty}>
                                    {savingConfig ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
                                    保存归档配置
                                </Button>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                            <div className="space-y-1 rounded-lg border bg-muted/30 p-4">
                                <p className="text-xs text-muted-foreground">存储开关</p>
                                <p className={`text-sm font-semibold ${saveEnabled ? "text-green-600" : "text-muted-foreground"}`}>
                                    {saveEnabled ? "已启用" : "已禁用"}
                                </p>
                            </div>
                            <div className="space-y-1 rounded-lg border bg-muted/30 p-4">
                                <p className="text-xs text-muted-foreground">已存文件</p>
                                <p className="text-sm font-semibold">{totalPages} 个 JSON</p>
                            </div>
                            <div className="space-y-1 rounded-lg border bg-muted/30 p-4">
                                <p className="text-xs text-muted-foreground">占用磁盘</p>
                                <p className="text-sm font-semibold">{formatBytes(totalBytes)}</p>
                            </div>
                            <div className="space-y-1 rounded-lg border bg-muted/30 p-4">
                                <p className="text-xs text-muted-foreground">页数上限</p>
                                <p className="text-sm font-semibold">{maxPages === 0 ? "不限制" : `${maxPages} 页`}</p>
                            </div>
                        </div>

                        <div className="flex items-start gap-3 rounded-lg border border-border/50 bg-muted/20 p-4">
                            <HardDrive className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                            <div className="space-y-0.5">
                                <p className="text-xs text-muted-foreground">存储目录</p>
                                <p className="break-all font-mono text-sm">{storage.storage_dir}</p>
                            </div>
                        </div>

                        {storage.tasks.length > 0 && (
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <p className="flex items-center gap-1.5 text-sm font-medium">
                                        <FileText className="h-4 w-4 text-muted-foreground" /> 已归档任务 ({storage.tasks.length})
                                    </p>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="h-7 text-xs text-red-600"
                                        onClick={() => setConfirmClearAll(true)}
                                        disabled={clearingAll}
                                    >
                                        {clearingAll ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-1 h-3.5 w-3.5" />}
                                        清理全部
                                    </Button>
                                </div>
                                <div className="max-h-48 space-y-0 divide-y overflow-y-auto rounded-lg border">
                                    {storage.tasks.map((t) => (
                                        <div key={t.task_id} className="flex items-center justify-between gap-2 px-3 py-2.5 text-xs transition-colors hover:bg-muted/30">
                                            <span className="max-w-[55%] truncate font-mono text-foreground/80">{t.task_id}</span>
                                            <div className="ml-2 flex shrink-0 items-center gap-2">
                                                <span className="text-muted-foreground">{t.page_count} 页 · {formatBytes(t.total_bytes)}</span>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="h-6 px-2 text-[11px] text-red-600"
                                                    disabled={deletingTaskId === t.task_id}
                                                    onClick={() => setConfirmDeleteTaskId(t.task_id)}
                                                >
                                                    {deletingTaskId === t.task_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "清理"}
                                                </Button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </>
                ) : (
                    <div className="rounded-lg border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">
                        无法连接后端服务，请确认服务已启动。
                    </div>
                )}
            </CardContent>
            <ConfirmDialog
                open={Boolean(confirmDeleteTaskId)}
                title="确认清理该任务归档？"
                description="该任务的所有原始 JSON 将被删除，此操作不可撤销。"
                confirmText="确认清理"
                cancelText="取消"
                onCancel={() => setConfirmDeleteTaskId(null)}
                onConfirm={async () => {
                    if (!confirmDeleteTaskId) return;
                    const taskId = confirmDeleteTaskId;
                    setConfirmDeleteTaskId(null);
                    await handleDeleteTask(taskId);
                }}
            />
            <ConfirmDialog
                open={confirmClearAll}
                title="确认清理全部归档？"
                description="所有任务原始响应将被删除，仅影响归档文件，不影响任务结果。"
                confirmText="全部清理"
                cancelText="取消"
                onCancel={() => setConfirmClearAll(false)}
                onConfirm={async () => {
                    setConfirmClearAll(false);
                    await handleClearAll();
                }}
            />
        </Card>
    );
}
