"use client";
import * as React from "react";
import { CheckCircle2, Globe, Loader2, RefreshCw, Trash2, XCircle } from "lucide-react";
import { api } from "@/services/api";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

export function WeiboCookieManager() {
    const { push } = useToast();
    const [loading, setLoading] = React.useState(false);
    const [status, setStatus] = React.useState<{
        cookies: { name: string; masked: string }[];
        has_login: boolean;
        count: number;
    } | null>(null);
    const [rawCookie, setRawCookie] = React.useState("");
    const [saving, setSaving] = React.useState(false);
    const [confirmClear, setConfirmClear] = React.useState(false);

    const loadStatus = React.useCallback(async () => {
        setLoading(true);
        try {
            const data = await api.weiboCookies.list();
            setStatus(data);
        } catch {
            push({ title: "加载失败", description: "无法获取微博 Cookie 状态", type: "error" });
        } finally {
            setLoading(false);
        }
    }, [push]);

    React.useEffect(() => {
        void loadStatus();
    }, [loadStatus]);

    const handleSave = async () => {
        if (!rawCookie.trim()) {
            push({ title: "请输入 Cookie", type: "error" });
            return;
        }
        setSaving(true);
        try {
            await api.weiboCookies.save({ raw_string: rawCookie.trim() });
            push({ title: "保存成功", description: "微博 Cookie 已保存", type: "success" });
            setRawCookie("");
            await loadStatus();
        } catch {
            push({ title: "保存失败", type: "error" });
        } finally {
            setSaving(false);
        }
    };

    const handleCapture = async () => {
        setLoading(true);
        try {
            const res = await api.weiboCookies.capture();
            if (res.captured > 0) {
                push({ title: "采集成功", description: `已采集 ${res.captured} 个微博 Cookie`, type: "success" });
                await loadStatus();
            } else {
                push({ title: "未采集到 Cookie", description: res.message || "请先在浏览器中登录微博", type: "info" });
            }
        } catch {
            push({ title: "采集失败", type: "error" });
        } finally {
            setLoading(false);
        }
    };

    const handleClear = async () => {
        try {
            await api.weiboCookies.clear();
            push({ title: "已清空", description: "微博 Cookie 已清空", type: "success" });
            await loadStatus();
        } catch {
            push({ title: "清空失败", type: "error" });
        }
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-border bg-muted/20 p-4 shadow-sm">
                <div className="flex items-center gap-3">
                    {loading ? (
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    ) : status?.has_login ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                    ) : (
                        <XCircle className="h-4 w-4 text-red-500" />
                    )}
                    <div>
                        <p className="text-sm font-medium text-foreground">
                            {loading ? "检测中..." : status?.has_login ? "已登录微博" : "未登录（缺少有效 Cookie）"}
                        </p>
                        <p className="text-xs text-muted-foreground">{status ? `当前保存 ${status.count} 个 Cookie` : "尚未读取 Cookie"}</p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => void loadStatus()} disabled={loading} className="rounded-md">
                        <RefreshCw className="h-3.5 w-3.5" />
                    </Button>
                    {status && status.count > 0 ? (
                        <Button variant="ghost" size="sm" onClick={() => setConfirmClear(true)} className="rounded-md text-red-500 hover:text-red-600">
                            <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                    ) : null}
                </div>
            </div>

            {status && status.cookies.length > 0 ? (
                <div className="max-h-36 space-y-1 overflow-y-auto rounded-lg border border-border bg-muted/20 p-3 shadow-sm">
                    {status.cookies.map((cookie) => (
                        <div key={cookie.name} className="flex items-center gap-2 rounded-lg bg-background px-3 py-2 text-xs font-mono shadow-sm">
                            <span className="w-20 shrink-0 font-semibold text-foreground">{cookie.name}</span>
                            <span className="truncate text-muted-foreground">{cookie.masked}</span>
                        </div>
                    ))}
                </div>
            ) : null}

            <div className="rounded-lg border border-border bg-background p-4 shadow-sm">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <p className="text-sm font-medium text-foreground">从浏览器采集</p>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">需要先在本机浏览器中完成微博登录，再点击下方按钮。</p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => void handleCapture()} disabled={loading} className="gap-1.5 rounded-md">
                        <Globe className="h-3.5 w-3.5" />
                        从浏览器采集
                    </Button>
                </div>
            </div>

            <div className="space-y-3 rounded-lg border border-border bg-background p-4 shadow-sm">
                <label className="text-sm font-medium text-foreground">手动粘贴 Cookie</label>
                <textarea
                    className="h-24 w-full resize-none rounded-md border border-input bg-background px-3 py-3 font-mono text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring placeholder:text-muted-foreground"
                    placeholder="粘贴 document.cookie 内容，如：SUB=xxx; SUBP=xxx; XSRF-TOKEN=xxx"
                    value={rawCookie}
                    onChange={(e) => setRawCookie(e.target.value)}
                />
                <div className="flex justify-end">
                    <Button size="sm" onClick={() => void handleSave()} disabled={!rawCookie.trim() || saving} className="gap-1.5 rounded-md">
                        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                        保存 Cookie
                    </Button>
                </div>
            </div>

            <ConfirmDialog
                open={confirmClear}
                title="确认清空微博 Cookie？"
                description="清空后微博平台相关任务将无法继续使用当前登录态。"
                confirmText="确认清空"
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
