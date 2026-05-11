"use client";
import * as React from "react";
import {
    ChevronDown,
    ChevronUp,
    Info,
    Loader2,
    RefreshCw,
    ShieldCheck,
    Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { api, WeiboAccountOut } from "@/services/api";
import { cn } from "@/lib/utils";

export function WeiboAccountPoolCard() {
    const { push } = useToast();
    const [accounts, setAccounts] = React.useState<WeiboAccountOut[]>([]);
    const [loading, setLoading] = React.useState(true);
    const [validatingId, setValidatingId] = React.useState<string | null>(null);
    const [confirmDeleteId, setConfirmDeleteId] = React.useState<string | null>(null);
    const [deleting, setDeleting] = React.useState(false);

    const showToast = React.useCallback((type: "success" | "error" | "info", title: string, description?: string) => {
        push({ type, title, description });
    }, [push]);

    const fetchData = React.useCallback(async () => {
        setLoading(true);
        try {
            const accountList = await api.weiboAccounts.list();
            setAccounts(accountList);
        } catch (error) {
            showToast("error", "加载微博账号池失败", error instanceof Error ? error.message : String(error));
        } finally {
            setLoading(false);
        }
    }, [showToast]);

    React.useEffect(() => {
        void fetchData();
    }, [fetchData]);

    const handleToggleEnabled = async (account: WeiboAccountOut) => {
        try {
            await api.weiboAccounts.update(account.account_id, { enabled: !account.enabled });
            setAccounts((prev) => prev.map((item) => item.account_id === account.account_id ? { ...item, enabled: !item.enabled } : item));
            showToast("info", `微博账号"${account.alias}"已${!account.enabled ? "启用" : "停用"}`);
        } catch (error) {
            showToast("error", "切换账号状态失败", error instanceof Error ? error.message : String(error));
        }
    };

    const handleValidate = async (accountId: string) => {
        setValidatingId(accountId);
        try {
            const updated = await api.weiboAccounts.validate(accountId);
            setAccounts((prev) => prev.map((item) => item.account_id === accountId ? updated : item));
            showToast(
                updated.is_valid ? "success" : "error",
                updated.is_valid ? "微博账号验证通过" : "微博账号验证失败",
                updated.is_valid ? "当前 Cookie 可继续使用。" : "Cookie 可能已过期，建议重新录入。"
            );
        } catch (error) {
            showToast("error", "验证失败", error instanceof Error ? error.message : String(error));
        } finally {
            setValidatingId(null);
        }
    };

    const handleDelete = async () => {
        if (!confirmDeleteId) return;
        setDeleting(true);
        try {
            await api.weiboAccounts.delete(confirmDeleteId);
            setAccounts((prev) => prev.filter((item) => item.account_id !== confirmDeleteId));
            showToast("success", "微博账号已删除");
            await fetchData();
        } catch (error) {
            showToast("error", "删除失败", error instanceof Error ? error.message : String(error));
        } finally {
            setDeleting(false);
            setConfirmDeleteId(null);
        }
    };

    const formatTime = (timestamp: number) => {
        if (!timestamp) return "从未";
        return new Date(timestamp * 1000).toLocaleString("zh-CN", {
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        });
    };

    return (
        <div className="space-y-4">
            <div className="space-y-3">
                {loading ? (
                    <div className="flex items-center gap-2 rounded-lg border border-border bg-background p-4 text-sm text-muted-foreground shadow-sm">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在加载微博账号池...
                    </div>
                ) : accounts.length === 0 ? (
                    <div className="flex items-start gap-2.5 rounded-lg border border-orange-500/20 bg-orange-500/5 px-4 py-4 text-sm text-orange-700 shadow-sm dark:text-orange-400">
                        <Info className="mt-0.5 h-4 w-4 shrink-0" />
                        <p>在上方「微博 Cookie 管理」中保存 Cookie 后，账号会自动同步到这里，无需手动添加。</p>
                    </div>
                ) : (
                    accounts.map((account) => (
                        <div key={account.account_id} className="rounded-lg border border-border bg-background p-4 shadow-sm">
                            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <span className="text-sm font-semibold text-foreground">{account.alias}</span>
                                        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", account.enabled ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground")}>
                                            {account.enabled ? "已启用" : "已停用"}
                                        </span>
                                        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", account.is_valid ? "bg-blue-500/10 text-blue-600" : "bg-red-500/10 text-red-600")}>
                                            {account.is_valid ? "凭证有效" : "凭证失效"}
                                        </span>
                                        {account.is_rate_limited ? <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600">限速中</span> : null}
                                    </div>
                                    <p className="mt-1 text-xs text-muted-foreground">{account.cookie_count} 条 Cookie</p>

                                    <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                                        <MiniStat label="使用次数" value={`${account.use_count}`} />
                                        <MiniStat label="失败次数" value={`${account.fail_count}`} accent={account.fail_count > 0 ? "text-amber-600" : undefined} />
                                        <MiniStat label="上次使用" value={formatTime(account.last_used_at)} />
                                        <MiniStat label="上次验证" value={formatTime(account.last_validated_at)} />
                                    </div>

                                    {account.is_rate_limited ? (
                                        <p className="mt-2 text-xs text-amber-600">限速恢复时间：{formatTime(account.rate_reset_at)}</p>
                                    ) : null}
                                </div>

                                <div className="flex items-center gap-2 lg:ml-4">
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="rounded-md"
                                        onClick={() => void handleValidate(account.account_id)}
                                        disabled={validatingId === account.account_id}
                                        title="验证账号登录状态"
                                    >
                                        {validatingId === account.account_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="rounded-md"
                                        onClick={() => void handleToggleEnabled(account)}
                                        title={account.enabled ? "停用账号" : "启用账号"}
                                    >
                                        {account.enabled ? <ChevronUp className="h-3.5 w-3.5 text-emerald-500" /> : <ChevronDown className="h-3.5 w-3.5 text-slate-400" />}
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="rounded-md text-red-500 hover:text-red-600"
                                        onClick={() => setConfirmDeleteId(account.account_id)}
                                        title="删除账号"
                                    >
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                </div>
                            </div>
                        </div>
                    ))
                )}
            </div>

            <div className="flex items-center justify-end">
                <Button size="sm" variant="ghost" className="gap-1.5 rounded-md text-muted-foreground" onClick={() => void fetchData()} disabled={loading}>
                    <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
                    刷新
                </Button>
            </div>

            <ConfirmDialog
                open={confirmDeleteId !== null}
                title="删除微博账号"
                description="确定要删除该微博账号吗？此操作不可撤销，账号的所有 Cookie 数据将被清除。"
                confirmText={deleting ? "删除中..." : "确认删除"}
                cancelText="取消"
                onConfirm={handleDelete}
                onCancel={() => setConfirmDeleteId(null)}
            />
        </div>
    );
}

function MiniStat({ label, value, accent }: { label: string; value: string; accent?: string }) {
    return (
        <div className="rounded-md border border-border bg-muted/20 px-3 py-2 shadow-sm">
            <p className="text-[11px] text-muted-foreground">{label}</p>
            <p className={cn("mt-1 text-sm font-medium text-foreground", accent)}>{value}</p>
        </div>
    );
}
