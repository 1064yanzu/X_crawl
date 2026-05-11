"use client";

import * as React from "react";
import {
    CheckCircle2,
    ChevronUp,
    Clock,
    KeySquare,
    Loader2,
    Plus,
    RefreshCw,
    ShieldCheck,
    Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { api, type YouTubeApiKey } from "@/services/api";
import { cn } from "@/lib/utils";

function formatDateTime(iso: string | null | undefined): string {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleString("zh-CN", { hour12: false });
    } catch {
        return iso;
    }
}

function statusBadgeClass(status: string): string {
    if (status === "active") {
        return "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300";
    }
    if (status === "exhausted") {
        return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300";
    }
    return "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300";
}

function statusLabel(status: string): string {
    if (status === "active") return "可用";
    if (status === "exhausted") return "配额耗尽";
    if (status === "invalid") return "无效";
    return status;
}

export function YouTubeApiKeyManager() {
    const { push } = useToast();
    const [keys, setKeys] = React.useState<YouTubeApiKey[]>([]);
    const [loading, setLoading] = React.useState(true);
    const [addOpen, setAddOpen] = React.useState(false);
    const [submitting, setSubmitting] = React.useState(false);
    const [newAlias, setNewAlias] = React.useState("");
    const [newKey, setNewKey] = React.useState("");
    const [validatingId, setValidatingId] = React.useState<string | null>(null);
    const [deleteTarget, setDeleteTarget] = React.useState<YouTubeApiKey | null>(null);
    const [deleting, setDeleting] = React.useState(false);

    const notify = React.useCallback(
        (type: "success" | "error" | "info", title: string, description?: string) => {
            push({ type, title, description });
        },
        [push],
    );

    const refresh = React.useCallback(async () => {
        setLoading(true);
        try {
            const list = await api.youtubeApiKeys.list();
            setKeys(list);
        } catch (error) {
            notify("error", "加载 YouTube API Key 失败", error instanceof Error ? error.message : String(error));
        } finally {
            setLoading(false);
        }
    }, [notify]);

    React.useEffect(() => {
        void refresh();
    }, [refresh]);

    const submitAdd = async (e: React.FormEvent) => {
        e.preventDefault();
        const alias = newAlias.trim();
        const apiKey = newKey.trim();
        if (!apiKey) {
            notify("error", "请填写 API Key");
            return;
        }
        setSubmitting(true);
        try {
            await api.youtubeApiKeys.add({
                alias: alias || `Key-${Date.now().toString(36)}`,
                api_key: apiKey,
                enabled: true,
            });
            notify("success", "已添加 API Key");
            setNewAlias("");
            setNewKey("");
            setAddOpen(false);
            await refresh();
        } catch (error) {
            notify("error", "添加失败", error instanceof Error ? error.message : String(error));
        } finally {
            setSubmitting(false);
        }
    };

    const toggleEnabled = async (key: YouTubeApiKey) => {
        try {
            await api.youtubeApiKeys.update(key.key_id, { enabled: !key.enabled });
            setKeys((prev) => prev.map((item) => (item.key_id === key.key_id ? { ...item, enabled: !item.enabled } : item)));
            notify("info", `${key.alias} 已${!key.enabled ? "启用" : "停用"}`);
        } catch (error) {
            notify("error", "切换状态失败", error instanceof Error ? error.message : String(error));
        }
    };

    const validateKey = async (key: YouTubeApiKey) => {
        setValidatingId(key.key_id);
        try {
            const result = await api.youtubeApiKeys.validate(key.key_id);
            notify(
                result.ok ? "success" : "error",
                result.ok ? `${key.alias} 验证通过` : `${key.alias} 验证失败`,
                result.ok ? "Key 可用，已重置失败计数。" : result.message || result.reason || "未知错误",
            );
            await refresh();
        } catch (error) {
            notify("error", "验证请求失败", error instanceof Error ? error.message : String(error));
        } finally {
            setValidatingId(null);
        }
    };

    const doDelete = async () => {
        if (!deleteTarget) return;
        setDeleting(true);
        try {
            await api.youtubeApiKeys.delete(deleteTarget.key_id);
            notify("success", `${deleteTarget.alias} 已删除`);
            setDeleteTarget(null);
            await refresh();
        } catch (error) {
            notify("error", "删除失败", error instanceof Error ? error.message : String(error));
        } finally {
            setDeleting(false);
        }
    };

    return (
        <Card className="rounded-lg border-border bg-card ">
            <CardHeader className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
                <div>
                    <CardTitle className="flex items-center gap-2 text-xl">
                        <KeySquare className="h-5 w-5 text-red-600 dark:text-red-400" />
                        API Key 池
                    </CardTitle>
                    <CardDescription className="mt-1">
                        多 Key 轮询降低单 Key 每日 10,000 配额的约束。建议每个 Key 都单独命名，便于定位问题。
                    </CardDescription>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" className="rounded-md" onClick={refresh} disabled={loading}>
                        <RefreshCw className={cn("mr-1 h-4 w-4", loading && "animate-spin")} />
                        刷新
                    </Button>
                    <Button size="sm" className="rounded-md" onClick={() => setAddOpen((v) => !v)}>
                        {addOpen ? <ChevronUp className="mr-1 h-4 w-4" /> : <Plus className="mr-1 h-4 w-4" />}
                        {addOpen ? "收起" : "添加 Key"}
                    </Button>
                </div>
            </CardHeader>

            <CardContent className="space-y-4 pt-5">
                {addOpen && (
                    <form
                        onSubmit={submitAdd}
                        className="grid gap-3 rounded-md border border-border bg-background p-4 sm:grid-cols-[1fr_2fr_auto]"
                    >
                        <Input
                            value={newAlias}
                            placeholder="备注（如 主账号 / 备用-01）"
                            onChange={(e) => setNewAlias(e.target.value)}
                            maxLength={60}
                        />
                        <Input
                            value={newKey}
                            placeholder="粘贴 YouTube Data API v3 Key"
                            onChange={(e) => setNewKey(e.target.value)}
                            required
                        />
                        <Button type="submit" disabled={submitting} className="rounded-md">
                            {submitting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Plus className="mr-1 h-4 w-4" />}
                            保存
                        </Button>
                    </form>
                )}

                {loading ? (
                    <div className="flex items-center justify-center gap-2 rounded-md border border-dashed border-border bg-background p-8 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在加载 Key 列表...
                    </div>
                ) : keys.length === 0 ? (
                    <div className="rounded-md border border-dashed border-border bg-background p-8 text-center">
                        <ShieldCheck className="mx-auto h-8 w-8 text-muted-foreground" />
                        <p className="mt-3 text-sm text-muted-foreground">
                            尚未添加任何 YouTube API Key。添加后才能创建 YouTube 采集任务。
                        </p>
                    </div>
                ) : (
                    <ul className="space-y-3">
                        {keys.map((key) => {
                            const used = key.quota_used_today;
                            const limit = key.daily_quota_limit || 10000;
                            const pct = Math.min(100, Math.round((used / Math.max(1, limit)) * 100));
                            return (
                                <li
                                    key={key.key_id}
                                    className="rounded-md border border-border bg-background p-4 shadow-sm"
                                >
                                    <div className="flex flex-wrap items-center gap-3">
                                        <span className="inline-flex items-center gap-2 rounded-md bg-muted/60 px-3 py-1.5 text-sm font-medium">
                                            <KeySquare className="h-4 w-4 text-red-600 dark:text-red-400" />
                                            {key.alias}
                                        </span>
                                        <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-semibold", statusBadgeClass(key.status))}>
                                            {statusLabel(key.status)}
                                        </span>
                                        <span className="font-mono text-xs text-muted-foreground">{key.api_key_masked}</span>
                                        <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
                                            <Clock className="h-3.5 w-3.5" />
                                            下次重置 {formatDateTime(key.quota_reset_at)}
                                        </span>
                                    </div>

                                    <div className="mt-3">
                                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                                            <span>今日配额</span>
                                            <span>
                                                {used.toLocaleString()} / {limit.toLocaleString()} · 剩余 {key.quota_remaining.toLocaleString()}
                                            </span>
                                        </div>
                                        <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted">
                                            <div
                                                className={cn(
 "h-full rounded-full transition-all",
                                                    pct >= 95
                                                        ? "bg-rose-500"
                                                        : pct >= 75
                                                          ? "bg-amber-500"
                                                          : "bg-emerald-500",
                                                )}
                                                style={{ width: `${pct}%` }}
                                            />
                                        </div>
                                    </div>

                                    {key.last_error && (
                                        <p className="mt-2 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
                                            最近错误：{key.last_error}
                                        </p>
                                    )}

                                    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                        <span>最近使用：{formatDateTime(key.last_used_at)}</span>
                                        <span>·</span>
                                        <span>最近验证：{formatDateTime(key.last_validated_at)}</span>
                                        {key.fail_count > 0 && (
                                            <>
                                                <span>·</span>
                                                <span className="text-rose-600 dark:text-rose-400">失败次数 {key.fail_count}</span>
                                            </>
                                        )}

                                        <div className="ml-auto flex items-center gap-2">
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="rounded-md"
                                                onClick={() => toggleEnabled(key)}
                                            >
                                                {key.enabled ? "停用" : "启用"}
                                            </Button>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="rounded-md"
                                                onClick={() => validateKey(key)}
                                                disabled={validatingId === key.key_id}
                                            >
                                                {validatingId === key.key_id ? (
                                                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                                                ) : (
                                                    <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                                                )}
                                                验证
                                            </Button>
                                            <Button
                                                size="sm"
                                                variant="destructive"
                                                className="rounded-md"
                                                onClick={() => setDeleteTarget(key)}
                                            >
                                                <Trash2 className="mr-1 h-3.5 w-3.5" />
                                                删除
                                            </Button>
                                        </div>
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </CardContent>

            <ConfirmDialog
                open={deleteTarget !== null}
                title={`确认删除 ${deleteTarget?.alias}？`}
                description="删除后正在运行的 YouTube 任务如依赖该 Key，将会切到其他可用 Key；若无其他 Key 则会暂停等待配置。"
                confirmText={deleting ? "删除中..." : "删除"}
                cancelText="取消"
                onConfirm={doDelete}
                onCancel={() => setDeleteTarget(null)}
            />
        </Card>
    );
}
