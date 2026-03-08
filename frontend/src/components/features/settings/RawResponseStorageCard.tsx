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

    const totalBytes = storage?.tasks.reduce((sum, task) => sum + task.total_bytes, 0) ?? 0;
    const totalPages = storage?.tasks.reduce((sum, task) => sum + task.page_count, 0) ?? 0;
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
            push({ type: "error", title: "保存失败", description: err instanceof Error ? err.message : String(err) });
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
            push({ type: "error", title: "清理失败", description: err instanceof Error ? err.message : String(err) });
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
            push({ type: "error", title: "清理失败", description: err instanceof Error ? err.message : String(err) });
        } finally {
            setClearingAll(false);
        }
    };

    return (
        <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl"><DatabaseBackup className="h-5 w-5 text-green-600" /> 原始响应存储</CardTitle>
                <CardDescription>管理搜索与回复原始 JSON 的本地归档配置、容量占用和历史清理。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {loading ? (
                    <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在读取存储信息...
                    </div>
                ) : storage ? (
                    <>
                        <div className="space-y-4 rounded-[1.25rem] border border-border/60 bg-muted/20 p-4 shadow-sm">
                            <ToggleSetting
                                label="保存原始响应"
                                description="关闭后不再写入新的 raw JSON，只保留已有归档。"
                                checked={saveEnabled}
                                onChange={setSaveEnabled}
                            />

                            <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-background/70 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                                <div>
                                    <p className="text-sm font-medium text-foreground">每任务最大保存页数</p>
                                    <p className="mt-1 text-xs leading-5 text-muted-foreground">输入 0 表示不限制；建议仅在排查问题时拉高该值。</p>
                                </div>
                                <div className="flex items-center gap-2">
                                    <input
                                        type="number"
                                        min={0}
                                        step={1}
                                        value={maxPages}
                                        onChange={(e) => setMaxPages(Math.max(0, Number(e.target.value) || 0))}
                                        className="h-11 w-28 rounded-xl border border-input bg-background px-3 font-mono text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                    />
                                    <span className="text-xs text-muted-foreground">页</span>
                                </div>
                            </div>

                            <div className="flex justify-end rounded-[1.25rem] border border-border/60 bg-background/70 p-4 shadow-sm">
                                <Button size="sm" onClick={handleSaveConfig} disabled={savingConfig || !isConfigDirty} className="rounded-xl">
                                    {savingConfig ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
                                    保存归档配置
                                </Button>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                            <StatItem label="存储开关" value={saveEnabled ? "已启用" : "已禁用"} accent={saveEnabled ? "text-emerald-600" : undefined} />
                            <StatItem label="已存文件" value={`${totalPages} 个 JSON`} />
                            <StatItem label="占用磁盘" value={formatBytes(totalBytes)} />
                            <StatItem label="页数上限" value={maxPages === 0 ? "不限制" : `${maxPages} 页`} />
                        </div>

                        <div className="flex items-start gap-3 rounded-[1.25rem] border border-border/60 bg-muted/20 p-4 shadow-sm">
                            <HardDrive className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                            <div className="space-y-1">
                                <p className="text-xs text-muted-foreground">存储目录</p>
                                <p className="break-all font-mono text-sm text-foreground">{storage.storage_dir}</p>
                            </div>
                        </div>

                        {storage.tasks.length > 0 ? (
                            <div className="space-y-3 rounded-[1.25rem] border border-border/60 bg-background/70 p-4 shadow-sm">
                                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                    <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                                        <FileText className="h-4 w-4 text-muted-foreground" /> 已归档任务 ({storage.tasks.length})
                                    </p>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="rounded-xl text-red-600"
                                        onClick={() => setConfirmClearAll(true)}
                                        disabled={clearingAll}
                                    >
                                        {clearingAll ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-1 h-3.5 w-3.5" />}
                                        清理全部
                                    </Button>
                                </div>
                                <div className="max-h-56 divide-y overflow-y-auto rounded-2xl border border-border/60 bg-card/80">
                                    {storage.tasks.map((task) => (
                                        <div key={task.task_id} className="flex items-center justify-between gap-3 px-4 py-3 text-xs transition-colors hover:bg-muted/20">
                                            <div className="min-w-0">
                                                <p className="truncate font-mono text-foreground">{task.task_id}</p>
                                                <p className="mt-1 text-muted-foreground">{task.page_count} 页 · {formatBytes(task.total_bytes)}</p>
                                            </div>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="rounded-xl text-red-600"
                                                disabled={deletingTaskId === task.task_id}
                                                onClick={() => setConfirmDeleteTaskId(task.task_id)}
                                            >
                                                {deletingTaskId === task.task_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "清理"}
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ) : null}
                    </>
                ) : (
                    <div className="rounded-2xl border border-dashed border-border/80 bg-muted/20 p-4 text-sm text-muted-foreground">
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

function ToggleSetting({
    label,
    description,
    checked,
    onChange,
}: {
    label: string;
    description: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
}) {
    return (
        <label className="flex items-start justify-between gap-3 rounded-2xl border border-border/60 bg-background/70 p-4 shadow-sm">
            <div>
                <p className="text-sm font-medium text-foreground">{label}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
            </div>
            <span className="relative mt-0.5 inline-flex cursor-pointer items-center">
                <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
                <span className="h-6 w-11 rounded-full bg-muted transition-colors peer-checked:bg-primary" />
                <span className="absolute left-[2px] top-[2px] h-5 w-5 rounded-full border bg-white transition-transform peer-checked:translate-x-full" />
            </span>
        </label>
    );
}

function StatItem({ label, value, accent }: { label: string; value: string; accent?: string }) {
    return (
        <div className="rounded-2xl border border-border/60 bg-muted/20 p-4 shadow-sm">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={`mt-1 text-sm font-semibold ${accent ?? "text-foreground"}`}>{value}</p>
        </div>
    );
}
