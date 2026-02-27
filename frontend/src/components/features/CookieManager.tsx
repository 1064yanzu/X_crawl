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
    Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { api, CookieItem } from "@/services/api";

type ToastType = "success" | "error" | "info";
type Toast = { type: ToastType; message: string };

export function CookieManager() {
    const [cookies, setCookies] = React.useState<CookieItem[]>([]);
    const [count, setCount] = React.useState(0);
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);
    const [capturing, setCapturing] = React.useState(false);
    const [exporting, setExporting] = React.useState(false);
    const [toast, setToast] = React.useState<Toast | null>(null);
    const [expanded, setExpanded] = React.useState(false);
    const [confirmClear, setConfirmClear] = React.useState(false);

    const [inputMode, setInputMode] = React.useState<"string" | "json">("string");
    const [rawInput, setRawInput] = React.useState("");

    const showToast = (type: ToastType, message: string) => {
        setToast({ type, message });
        setTimeout(() => setToast(null), 4000);
    };

    const fetchCookies = React.useCallback(async () => {
        setLoading(true);
        try {
            const res = await api.cookies.list();
            setCookies(res.cookies);
            setCount(res.count);
        } catch {
            setCookies([]);
            setCount(0);
        } finally {
            setLoading(false);
        }
    }, []);

    React.useEffect(() => {
        fetchCookies();
    }, [fetchCookies]);

    const handleSave = async () => {
        if (!rawInput.trim()) {
            showToast("error", "请输入 Cookie 内容");
            return;
        }
        setSaving(true);
        try {
            const res = inputMode === "string" ? await api.cookies.saveRaw(rawInput.trim()) : await api.cookies.save(JSON.parse(rawInput.trim()));
            setCookies(res.cookies);
            setCount(res.count);
            setRawInput("");
            const loggedIn = res.cookies.some((c) => c.name === "auth_token") && res.cookies.some((c) => c.name === "twid");
            showToast("success", loggedIn ? "登录态已保存，下次爬取将自动注入" : `已保存 ${res.count} 条 Cookie（未检测到完整登录态）`);
        } catch (e: unknown) {
            showToast("error", e instanceof Error ? e.message : "保存失败，请检查格式");
        } finally {
            setSaving(false);
        }
    };

    const handleCapture = async () => {
        setCapturing(true);
        try {
            const res = await api.cookies.capture();
            showToast(res.captured > 0 ? "success" : "error", res.message);
            if (res.captured > 0) fetchCookies();
        } catch (e: unknown) {
            showToast("error", e instanceof Error ? e.message : "浏览器未启动或未登录");
        } finally {
            setCapturing(false);
        }
    };

    const handleClear = async () => {
        try {
            await api.cookies.clear();
            setCookies([]);
            setCount(0);
            showToast("info", "已清空所有 Cookie");
        } catch {
            showToast("error", "清除失败");
        }
    };

    const handleExport = async (format: "json" | "string") => {
        setExporting(true);
        try {
            if (format === "json") {
                await api.cookies.exportJson();
            } else {
                await api.cookies.exportString();
            }
            showToast("success", `Cookie 已导出为 ${format === "json" ? "JSON" : "字符串"} 格式`);
        } catch (e: unknown) {
            showToast("error", e instanceof Error ? e.message : "导出失败");
        } finally {
            setExporting(false);
        }
    };

    const isLoggedIn = cookies.some((c) => c.name === "auth_token") && cookies.some((c) => c.name === "twid");
    const hasAnyCookie = count > 0;
    const statusColor = isLoggedIn ? "text-green-600" : hasAnyCookie ? "text-amber-600" : "text-muted-foreground";
    const statusIcon = isLoggedIn ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" />
    ) : (
        <AlertCircle className={`h-4 w-4 shrink-0 ${hasAnyCookie ? "text-amber-500" : "text-muted-foreground"}`} />
    );

    return (
        <div className="space-y-4">
            {toast && (
                <div
                    className={`animate-in slide-in-from-top-2 flex items-center gap-2 rounded-lg border px-4 py-3 text-sm duration-300 ${toast.type === "success"
                            ? "border-green-200 bg-green-50 text-green-700 dark:border-green-800/50 dark:bg-green-950/30 dark:text-green-400"
                            : toast.type === "error"
                                ? "border-red-200 bg-red-50 text-red-700 dark:border-red-800/50 dark:bg-red-950/30 dark:text-red-400"
                                : "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800/50 dark:bg-blue-950/30 dark:text-blue-400"
                        }`}
                >
                    {toast.type === "success" ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <AlertCircle className="h-4 w-4 shrink-0" />}
                    {toast.message}
                </div>
            )}

            <div className="flex items-center justify-between rounded-lg border bg-muted/20 p-4">
                <div className="flex items-center gap-3">
                    {loading ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : statusIcon}
                    <div>
                        <p className={`text-sm font-medium ${statusColor}`}>
                            {loading ? "加载中..." : isLoggedIn ? "X 账号已登录 · 凭证有效" : hasAnyCookie ? "已存储凭证（登录态不完整）" : "未配置登录凭证"}
                        </p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                            {isLoggedIn ? "爬取时将自动注入登录态，无需打开浏览器" : hasAnyCookie ? "缺少 auth_token 或 twid，爬取时可能提示未登录" : "录入 Cookie 后可跳过浏览器手动登录步骤"}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {hasAnyCookie && (
                        <button onClick={() => setExpanded(!expanded)} className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground">
                            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                            {expanded ? "收起" : `查看明细 (${count})`}
                        </button>
                    )}
                    <Button variant="outline" size="sm" onClick={fetchCookies} disabled={loading}>
                        <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
                    </Button>
                </div>
            </div>

            {expanded && cookies.length > 0 && (
                <div className="animate-in slide-in-from-top-1 divide-y overflow-hidden rounded-lg border duration-200">
                    {cookies.map((c) => (
                        <div key={`${c.domain}-${c.name}`} className="flex items-center justify-between bg-muted/10 px-4 py-2.5 text-xs transition-colors hover:bg-muted/20">
                            <div className="flex items-center gap-2">
                                <Cookie className="h-3 w-3 shrink-0 text-muted-foreground" />
                                <span className="font-mono font-semibold text-foreground">{c.name}</span>
                                <span className="text-muted-foreground">{c.domain}</span>
                            </div>
                            <span className="font-mono text-muted-foreground/70">{c.value_masked}</span>
                        </div>
                    ))}
                </div>
            )}

            <div className="space-y-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-4">
                <div className="flex items-start gap-3">
                    <Globe className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
                    <div>
                        <p className="text-sm font-medium text-blue-700 dark:text-blue-400">从浏览器自动获取</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">若已在浏览器中登录 X，可一键采集并保存 Cookie。</p>
                    </div>
                </div>
                <Button variant="outline" size="sm" className="border-blue-300 text-blue-700 hover:bg-blue-50 dark:border-blue-700 dark:text-blue-400" onClick={handleCapture} disabled={capturing}>
                    {capturing ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Globe className="mr-2 h-3.5 w-3.5" />}
                    {capturing ? "采集中..." : "从浏览器自动获取 Cookie"}
                </Button>
            </div>

            <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">手动录入 Cookie</p>
                    <div className="flex items-center gap-1 overflow-hidden rounded-md border text-xs">
                        {(["string", "json"] as const).map((mode) => (
                            <button
                                key={mode}
                                onClick={() => {
                                    setInputMode(mode);
                                    setRawInput("");
                                }}
                                className={`px-3 py-1.5 transition-colors ${inputMode === mode ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted/50"}`}
                            >
                                {mode === "string" ? "字符串格式" : "JSON 格式"}
                            </button>
                        ))}
                    </div>
                </div>
                <textarea
                    value={rawInput}
                    onChange={(e) => setRawInput(e.target.value)}
                    placeholder={
                        inputMode === "string"
                            ? "auth_token=your_token_here; twid=your_twid_here; ct0=..."
                            : '[{"name":"auth_token","value":"xxx","domain":".x.com"},{"name":"twid","value":"yyy","domain":".x.com"}]'
                    }
                    className="h-28 w-full resize-none rounded-lg border border-input bg-muted/20 px-3 py-2.5 font-mono text-xs placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <p className="text-xs text-muted-foreground">
                    {inputMode === "string" ? "从浏览器开发者工具复制 Cookie，粘贴为 name=value; name=value 格式" : "JSON 数组格式，每项需包含 name、value、domain"}
                </p>
                <div className="flex items-center justify-between">
                    <Button size="sm" onClick={handleSave} disabled={saving || !rawInput.trim()}>
                        {saving ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Cookie className="mr-2 h-3.5 w-3.5" />}
                        {saving ? "保存中..." : "保存 Cookie"}
                    </Button>
                    <div className="flex items-center gap-2">
                        {hasAnyCookie && (
                            <>
                                <div className="relative">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="border-green-300 text-green-700 hover:bg-green-50 dark:border-green-700 dark:text-green-400 dark:hover:bg-green-950/20"
                                        onClick={() => handleExport("json")}
                                        disabled={exporting}
                                    >
                                        {exporting ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1.5 h-3.5 w-3.5" />}
                                        导出 JSON
                                    </Button>
                                </div>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="border-green-300 text-green-700 hover:bg-green-50 dark:border-green-700 dark:text-green-400 dark:hover:bg-green-950/20"
                                    onClick={() => handleExport("string")}
                                    disabled={exporting}
                                >
                                    {exporting ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1.5 h-3.5 w-3.5" />}
                                    导出文本
                                </Button>
                                <Button variant="ghost" size="sm" className="text-red-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/20" onClick={() => setConfirmClear(true)}>
                                    <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                                    清除登录态
                                </Button>
                            </>
                        )}
                    </div>
                </div>
            </div>

            <ConfirmDialog
                open={confirmClear}
                title="确定要清除所有持久化 Cookie 吗？"
                description="清除后下次爬取需重新录入登录态。"
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

