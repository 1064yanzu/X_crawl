"use client";
import * as React from "react";
import {
    AlertCircle,
    CheckCircle2,
    ChevronDown,
    ChevronUp,
    Cookie,
    Download,
    Globe,
    Loader2,
    RefreshCw,
    ShieldAlert,
    Trash2,
    User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { api, CookieAccount, CookiesResponse } from "@/services/api";
import { cn } from "@/lib/utils";

export function CookieManager() {
    const { push } = useToast();
    const [accounts, setAccounts] = React.useState<CookieAccount[]>([]);
    const [count, setCount] = React.useState(0);
    const [hasLogin, setHasLogin] = React.useState(false);
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);
    const [capturing, setCapturing] = React.useState(false);
    const [exporting, setExporting] = React.useState(false);
    const [confirmClear, setConfirmClear] = React.useState(false);
    const [expandedAccount, setExpandedAccount] = React.useState<string | null>(null);
    const [inputMode, setInputMode] = React.useState<"string" | "json">("string");
    const [rawInput, setRawInput] = React.useState("");

    const showToast = React.useCallback((type: "success" | "error" | "info", title: string, description?: string) => {
        push({ type, title, description });
    }, [push]);

    const applyResponse = React.useCallback((response: CookiesResponse) => {
        setAccounts(response.accounts ?? []);
        setCount(response.count);
        setHasLogin(response.has_login);
    }, []);

    const fetchCookies = React.useCallback(async () => {
        setLoading(true);
        try {
            const response = await api.cookies.list();
            applyResponse(response);
        } catch {
            setAccounts([]);
            setCount(0);
            setHasLogin(false);
        } finally {
            setLoading(false);
        }
    }, [applyResponse]);

    React.useEffect(() => {
        void fetchCookies();
    }, [fetchCookies]);

    const handleSave = async () => {
        if (!rawInput.trim()) {
            showToast("error", "请输入 Cookie 内容");
            return;
        }

        setSaving(true);
        try {
            const response = inputMode === "string"
                ? await api.cookies.saveRaw(rawInput.trim())
                : await api.cookies.save(JSON.parse(rawInput.trim()));
            applyResponse(response);
            setRawInput("");
            showToast(
                "success",
                response.has_login ? "登录态已保存" : "Cookie 已保存",
                response.has_login ? "后续抓取会自动注入登录态。" : `已保存 ${response.count} 条 Cookie，但登录态仍不完整。`,
            );
        } catch (error: unknown) {
            showToast("error", "保存失败", error instanceof Error ? error.message : "请检查格式后重试");
        } finally {
            setSaving(false);
        }
    };

    const handleCapture = async () => {
        setCapturing(true);
        try {
            const response = await api.cookies.capture();
            showToast(response.captured > 0 ? "success" : "info", response.message);
            if (response.captured > 0) {
                await fetchCookies();
            }
        } catch (error: unknown) {
            showToast("error", "采集失败", error instanceof Error ? error.message : "浏览器未启动或未登录");
        } finally {
            setCapturing(false);
        }
    };

    const handleClear = async () => {
        try {
            await api.cookies.clear();
            setAccounts([]);
            setCount(0);
            setHasLogin(false);
            setExpandedAccount(null);
            showToast("success", "已清空所有 X Cookie");
        } catch {
            showToast("error", "清除失败");
        }
    };

    const handleExport = async (format: "json" | "string") => {
        setExporting(true);
        try {
            if (format === "json") await api.cookies.exportJson();
            else await api.cookies.exportString();
            showToast("success", `已导出为${format === "json" ? " JSON" : " 文本"}格式`);
        } catch (error: unknown) {
            showToast("error", "导出失败", error instanceof Error ? error.message : undefined);
        } finally {
            setExporting(false);
        }
    };

    const hasAnyCookie = count > 0;
    const statusIcon = hasLogin
        ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
        : hasAnyCookie
            ? <ShieldAlert className="h-4 w-4 shrink-0 text-amber-500" />
            : <AlertCircle className="h-4 w-4 shrink-0 text-muted-foreground" />;

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between rounded-[1.25rem] border border-border/60 bg-muted/20 p-4 shadow-sm">
                <div className="flex items-center gap-3">
                    {loading ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : statusIcon}
                    <div>
                        <p className={cn("text-sm font-medium", hasLogin ? "text-emerald-700 dark:text-emerald-300" : hasAnyCookie ? "text-amber-700 dark:text-amber-300" : "text-foreground")}>
                            {loading ? "加载中..." : hasLogin ? "X 账号已登录 · 凭证有效" : hasAnyCookie ? "已存储凭证（登录态不完整）" : "未配置登录凭证"}
                        </p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                            {hasLogin ? "抓取时将自动注入登录态，无需手动打开浏览器登录。" : hasAnyCookie ? "缺少 auth_token 或 twid，后续抓取仍可能提示未登录。" : "录入 Cookie 后可直接跳过浏览器手动登录步骤。"}
                        </p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => void fetchCookies()} disabled={loading} className="rounded-xl">
                        <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
                    </Button>
                    {hasAnyCookie ? (
                        <Button variant="ghost" size="sm" onClick={() => setConfirmClear(true)} className="rounded-xl text-red-500 hover:text-red-600">
                            <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                    ) : null}
                </div>
            </div>

            {accounts.length > 0 ? (
                <div className="space-y-3">
                    {accounts.map((account) => {
                        const isExpanded = expandedAccount === account.user_id;
                        return (
                            <div key={account.user_id} className="overflow-hidden rounded-[1.25rem] border border-border/60 bg-background/70 shadow-sm">
                                <div className="flex items-center justify-between px-4 py-3">
                                    <button
                                        type="button"
                                        className="flex flex-1 items-center gap-3 text-left"
                                        onClick={() => setExpandedAccount(isExpanded ? null : account.user_id)}
                                    >
                                        <div className={cn("flex h-9 w-9 items-center justify-center rounded-full", account.has_login ? "bg-emerald-500/10 text-emerald-600" : "bg-amber-500/10 text-amber-500")}>
                                            <User className="h-4 w-4" />
                                        </div>
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <span className="text-sm font-semibold text-foreground">{account.user_id !== "unknown" ? `用户 ${account.user_id}` : "默认账号"}</span>
                                                <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", account.has_login ? "bg-emerald-500/10 text-emerald-600" : "bg-amber-500/10 text-amber-600")}>
                                                    {account.has_login ? "登录有效" : "登录态不完整"}
                                                </span>
                                            </div>
                                            <p className="mt-0.5 text-xs text-muted-foreground">{account.cookie_count} 条 Cookie</p>
                                        </div>
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setExpandedAccount(isExpanded ? null : account.user_id)}
                                        className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
                                    >
                                        {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                                        {isExpanded ? "收起" : "详情"}
                                    </button>
                                </div>

                                {isExpanded ? (
                                    <div className="border-t border-border/50 bg-muted/10 px-4 py-4">
                                        <div className="grid gap-2">
                                            {account.cookies.map((cookie) => (
                                                <div key={`${account.user_id}-${cookie.name}-${cookie.domain}`} className="rounded-xl border border-border/60 bg-background px-3 py-3 shadow-sm">
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        <span className="font-mono text-sm font-medium text-foreground">{cookie.name}</span>
                                                        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", cookie.category === "auth" ? "bg-blue-500/10 text-blue-600" : cookie.category === "session" ? "bg-violet-500/10 text-violet-600" : "bg-muted text-muted-foreground")}>
                                                            {cookie.category}
                                                        </span>
                                                        {cookie.is_critical ? <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-600">关键</span> : null}
                                                    </div>
                                                    <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{cookie.value_masked}</p>
                                                    <p className="mt-1 text-[11px] text-muted-foreground">域名：{cookie.domain}</p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ) : null}
                            </div>
                        );
                    })}
                </div>
            ) : null}

            <div className="rounded-[1.25rem] border border-border/60 bg-background/70 p-4 shadow-sm">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <p className="text-sm font-medium text-foreground">从浏览器自动获取 Cookie</p>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">若已在浏览器中登录 X，可一键采集并保存当前 Cookie。</p>
                    </div>
                    <Button variant="outline" size="sm" className="rounded-xl border-blue-300 text-blue-700 hover:bg-blue-50 dark:border-blue-700 dark:text-blue-400 dark:hover:bg-blue-950/20" onClick={() => void handleCapture()} disabled={capturing}>
                        {capturing ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Globe className="mr-2 h-3.5 w-3.5" />}
                        {capturing ? "采集中..." : "从浏览器采集"}
                    </Button>
                </div>
            </div>

            <div className="space-y-3 rounded-[1.25rem] border border-border/60 bg-background/70 p-4 shadow-sm">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm font-medium text-foreground">手动录入 Cookie</p>
                    <div className="flex items-center gap-1 overflow-hidden rounded-xl border border-border/60 bg-muted/20 p-1 text-xs">
                        {(["string", "json"] as const).map((mode) => (
                            <button
                                key={mode}
                                type="button"
                                onClick={() => {
                                    setInputMode(mode);
                                    setRawInput("");
                                }}
                                className={cn("rounded-lg px-3 py-1.5 transition-colors", inputMode === mode ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-background")}
                            >
                                {mode === "string" ? "字符串格式" : "JSON 格式"}
                            </button>
                        ))}
                    </div>
                </div>
                <textarea
                    value={rawInput}
                    onChange={(e) => setRawInput(e.target.value)}
                    placeholder={inputMode === "string" ? "auth_token=...; twid=...; ct0=..." : '[{"name":"auth_token","value":"xxx","domain":".x.com"}]'}
                    className="h-28 w-full resize-none rounded-xl border border-input bg-muted/20 px-3 py-3 font-mono text-xs shadow-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <p className="text-xs text-muted-foreground">
                    {inputMode === "string" ? "从浏览器开发者工具复制 Cookie，粘贴为 name=value; name=value 格式。" : "JSON 数组格式，每项需包含 name、value、domain。"}
                </p>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <Button size="sm" onClick={() => void handleSave()} disabled={saving || !rawInput.trim()} className="rounded-xl">
                        {saving ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Cookie className="mr-2 h-3.5 w-3.5" />}
                        {saving ? "保存中..." : "保存 Cookie"}
                    </Button>
                    {hasAnyCookie ? (
                        <div className="flex items-center gap-2">
                            <Button variant="outline" size="sm" className="rounded-xl" onClick={() => void handleExport("json")} disabled={exporting}>
                                {exporting ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1.5 h-3.5 w-3.5" />}
                                导出 JSON
                            </Button>
                            <Button variant="outline" size="sm" className="rounded-xl" onClick={() => void handleExport("string")} disabled={exporting}>
                                {exporting ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1.5 h-3.5 w-3.5" />}
                                导出文本
                            </Button>
                        </div>
                    ) : null}
                </div>
            </div>

            <ConfirmDialog
                open={confirmClear}
                title="确定要清除全部 X Cookie 吗？"
                description="清除后下次抓取需要重新录入登录态，此操作不可撤销。"
                confirmText="确认清除"
                cancelText="取消"
                onCancel={() => setConfirmClear(false)}
                onConfirm={async () => {
                    setConfirmClear(false);
                    await handleClear();
                }}
            />
        </div>
    );
}
