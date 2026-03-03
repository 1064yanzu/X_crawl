"use client";
import * as React from "react";
import {
    AlertCircle,
    CheckCircle2,
    ChevronDown,
    ChevronUp,
    Clock,
    Info,
    Loader2,
    RefreshCw,
    ShieldCheck,
    Trash2,
    Users,
    Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { api, AccountOut, IntervalSuggestion } from "@/services/api";

type ToastType = "success" | "error" | "info";
type Toast = { type: ToastType; message: string };

export function AccountPoolCard() {
    const [accounts, setAccounts] = React.useState<AccountOut[]>([]);
    const [intervalSuggestion, setIntervalSuggestion] = React.useState<IntervalSuggestion | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [toast, setToast] = React.useState<Toast | null>(null);

    // 验证状态
    const [validatingId, setValidatingId] = React.useState<string | null>(null);

    // 删除确认
    const [confirmDeleteId, setConfirmDeleteId] = React.useState<string | null>(null);
    const [deleting, setDeleting] = React.useState(false);

    const showToast = (type: ToastType, message: string) => {
        setToast({ type, message });
        setTimeout(() => setToast(null), 4000);
    };

    const fetchData = React.useCallback(async () => {
        setLoading(true);
        try {
            const [accs, interval] = await Promise.all([
                api.accounts.list(),
                api.accounts.intervalSuggestion(),
            ]);
            setAccounts(accs);
            setIntervalSuggestion(interval);
        } catch (e) {
            showToast("error", `加载失败: ${e instanceof Error ? e.message : String(e)}`);
        } finally {
            setLoading(false);
        }
    }, []);

    React.useEffect(() => {
        fetchData();
    }, [fetchData]);


    const handleToggleEnabled = async (acc: AccountOut) => {
        try {
            await api.accounts.update(acc.account_id, { enabled: !acc.enabled });
            setAccounts((prev) =>
                prev.map((a) =>
                    a.account_id === acc.account_id ? { ...a, enabled: !a.enabled } : a
                )
            );
            showToast("info", `账号 "${acc.alias}" 已${!acc.enabled ? "启用" : "停用"}`);
        } catch (e) {
            showToast("error", `操作失败: ${e instanceof Error ? e.message : String(e)}`);
        }
    };

    const handleValidate = async (accountId: string) => {
        setValidatingId(accountId);
        try {
            const updated = await api.accounts.validate(accountId);
            setAccounts((prev) =>
                prev.map((a) => (a.account_id === accountId ? updated : a))
            );
            showToast(
                updated.is_valid ? "success" : "error",
                updated.is_valid ? `账号验证通过` : `账号验证失败（Cookie 可能已过期）`
            );
        } catch (e) {
            showToast("error", `验证失败: ${e instanceof Error ? e.message : String(e)}`);
        } finally {
            setValidatingId(null);
        }
    };

    const handleDelete = async () => {
        if (!confirmDeleteId) return;
        setDeleting(true);
        try {
            await api.accounts.delete(confirmDeleteId);
            setAccounts((prev) => prev.filter((a) => a.account_id !== confirmDeleteId));
            showToast("info", "账号已删除");
            await fetchData();
        } catch (e) {
            showToast("error", `删除失败: ${e instanceof Error ? e.message : String(e)}`);
        } finally {
            setDeleting(false);
            setConfirmDeleteId(null);
        }
    };

    const formatTime = (ts: number) => {
        if (!ts) return "从未";
        return new Date(ts * 1000).toLocaleString("zh-CN", {
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        });
    };

    return (
        <div className="space-y-4">
            {/* Toast */}
            {toast && (
                <div
                    className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm ${toast.type === "success"
                            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                            : toast.type === "error"
                                ? "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300"
                                : "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300"
                        }`}
                >
                    {toast.type === "success" ? (
                        <CheckCircle2 className="h-4 w-4 shrink-0" />
                    ) : (
                        <AlertCircle className="h-4 w-4 shrink-0" />
                    )}
                    {toast.message}
                </div>
            )}

            {/* 间隔建议区域 */}
            {intervalSuggestion && (
                <div className="rounded-lg border border-dashed bg-muted/30 p-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm font-medium">
                            <Zap className="h-4 w-4 text-amber-500" />
                            <span>当前动态间隔建议</span>
                        </div>
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Users className="h-3 w-3" />
                            {intervalSuggestion.active_account_count}/{intervalSuggestion.total_account_count} 活跃
                        </span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                        <div className="rounded bg-background px-2 py-1.5">
                            <span className="font-medium text-foreground">搜索接口</span>
                            <br />约 {intervalSuggestion.search_safe_interval}s（{intervalSuggestion.search_interval_min}~{intervalSuggestion.search_interval_max}s）
                        </div>
                        <div className="rounded bg-background px-2 py-1.5">
                            <span className="font-medium text-foreground">评论接口</span>
                            <br />约 {intervalSuggestion.tweet_detail_safe_interval}s（{intervalSuggestion.tweet_detail_interval_min}~{intervalSuggestion.tweet_detail_interval_max}s）
                        </div>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">{intervalSuggestion.note}</p>
                </div>
            )}

            {/* 账号列表 */}
            <div className="space-y-2">
                {loading ? (
                    <div className="flex items-center justify-center py-8 text-muted-foreground">
                        <Loader2 className="h-5 w-5 animate-spin" />
                        <span className="ml-2 text-sm">加载中...</span>
                    </div>
                ) : accounts.length === 0 ? (
                    <div className="rounded-lg border border-dashed py-8 text-center text-sm text-muted-foreground">
                        暂无账号，添加第一个账号以开启多账号协作模式
                    </div>
                ) : (
                    accounts.map((acc) => (
                        <div
                            key={acc.account_id}
                            className={`rounded-lg border p-3 transition-colors ${acc.enabled && acc.is_valid
                                    ? "bg-background"
                                    : "bg-muted/30 opacity-60"
                                }`}
                        >
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    {/* 状态指示点 */}
                                    <div
                                        className={`h-2 w-2 rounded-full ${acc.is_rate_limited
                                                ? "bg-amber-500"
                                                : acc.is_valid && acc.enabled
                                                    ? "bg-emerald-500"
                                                    : "bg-slate-300 dark:bg-slate-600"
                                            }`}
                                        title={
                                            acc.is_rate_limited
                                                ? "速率限制中"
                                                : acc.is_valid && acc.enabled
                                                    ? "活跃"
                                                    : "未启用/无效"
                                        }
                                    />
                                    <span className="text-sm font-medium">{acc.alias}</span>
                                    <span className="text-xs text-muted-foreground">
                                        {acc.cookie_count} 条 Cookie
                                        {acc.cookie_domains.length > 0 && ` · ${acc.cookie_domains.join(", ")}`}
                                    </span>
                                </div>

                                <div className="flex items-center gap-1">
                                    {/* 验证按钮 */}
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 px-2 text-xs"
                                        onClick={() => handleValidate(acc.account_id)}
                                        disabled={validatingId === acc.account_id}
                                        title="验证账号登录状态"
                                    >
                                        {validatingId === acc.account_id ? (
                                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                        ) : (
                                            <ShieldCheck className="h-3.5 w-3.5" />
                                        )}
                                    </Button>

                                    {/* 启用/停用 */}
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 px-2 text-xs"
                                        onClick={() => handleToggleEnabled(acc)}
                                        title={acc.enabled ? "停用账号" : "启用账号"}
                                    >
                                        {acc.enabled ? (
                                            <ChevronUp className="h-3.5 w-3.5 text-emerald-500" />
                                        ) : (
                                            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                                        )}
                                    </Button>

                                    {/* 删除 */}
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 px-2 text-xs text-red-500 hover:text-red-600"
                                        onClick={() => setConfirmDeleteId(acc.account_id)}
                                        title="删除账号"
                                    >
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                </div>
                            </div>

                            {/* 账号统计 */}
                            <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
                                <span>使用 {acc.use_count} 次</span>
                                {acc.fail_count > 0 && (
                                    <span className="text-amber-600">失败 {acc.fail_count} 次</span>
                                )}
                                {acc.last_used_at > 0 && (
                                    <span className="flex items-center gap-1">
                                        <Clock className="h-3 w-3" />
                                        上次使用 {formatTime(acc.last_used_at)}
                                    </span>
                                )}
                                {acc.is_rate_limited && (
                                    <span className="text-amber-600">
                                        限速中（至 {formatTime(acc.rate_reset_at)}）
                                    </span>
                                )}
                                {!acc.is_valid && (
                                    <span className="text-red-500">Cookie 无效</span>
                                )}
                            </div>
                        </div>
                    ))
                )}
            </div>
            {/* 自动同步提示 */}
            {accounts.length === 0 && !loading && (
                <div className="flex items-start gap-2.5 rounded-lg border border-blue-500/20 bg-blue-500/5 px-4 py-3 text-xs text-blue-700 dark:text-blue-400">
                    <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <p>在上方「Cookie 管理」中保存 Cookie 后，账号会自动同步到此处。无需手动添加。</p>
                </div>
            )}

            {/* 底部操作栏 */}
            <div className="flex items-center justify-end">
                <Button
                    size="sm"
                    variant="ghost"
                    className="gap-1.5 text-muted-foreground"
                    onClick={fetchData}
                    disabled={loading}
                >
                    <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                    刷新
                </Button>
            </div>

            {/* 删除确认对话框 */}
            <ConfirmDialog
                open={confirmDeleteId !== null}
                title="删除账号"
                description="确定要删除该账号吗？此操作不可撤销，账号的所有 Cookie 数据将被清除。"
                confirmText={deleting ? "删除中..." : "确认删除"}
                cancelText="取消"
                onConfirm={handleDelete}
                onCancel={() => setConfirmDeleteId(null)}
            />
        </div>
    );
}
