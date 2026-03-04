"use client";
import * as React from "react";
import { api } from "@/services/api";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { CheckCircle2, XCircle, Loader2, RefreshCw, Trash2, Globe } from "lucide-react";

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

    const loadStatus = React.useCallback(async () => {
        setLoading(true);
        try {
            const data = await api.weiboCookies.list();
            setStatus(data);
        } catch {
            push({ title: "加载失败", description: "无法读取微博 Cookie 状态", type: "error" });
        } finally {
            setLoading(false);
        }
    }, [push]);

    React.useEffect(() => { loadStatus(); }, [loadStatus]);

    const handleSave = async () => {
        if (!rawCookie.trim()) return;
        setSaving(true);
        try {
            const res = await api.weiboCookies.save({ raw_string: rawCookie.trim() });
            push({
                title: "保存成功",
                description: `已保存 ${res.saved} 个 Cookie${res.has_login ? "，登录状态：已登录" : ""}`,
                type: "success",
            });
            setRawCookie("");
            loadStatus();
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
                push({
                    title: "采集成功",
                    description: `已采集 ${res.captured} 个微博 Cookie`,
                    type: "success",
                });
                loadStatus();
            } else {
                push({
                    title: "未采集到 Cookie",
                    description: res.message || "请先在浏览器中登录微博",
                    type: "info",
                });
            }
        } catch {
            push({ title: "采集失败", type: "error" });
        } finally {
            setLoading(false);
        }
    };

    const handleClear = async () => {
        if (!confirm("确认清空所有微博 Cookie？")) return;
        try {
            await api.weiboCookies.clear();
            push({ title: "已清空", description: "微博 Cookie 已清空", type: "success" });
            loadStatus();
        } catch {
            push({ title: "清空失败", type: "error" });
        }
    };

    return (
        <div className="space-y-4">
            {/* 登录状态 */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    {loading ? (
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    ) : status?.has_login ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                    ) : (
                        <XCircle className="h-4 w-4 text-red-500" />
                    )}
                    <span className="text-sm font-medium">
                        {loading ? "检测中..." : status?.has_login ? "已登录微博" : "未登录（缺少有效 Cookie）"}
                    </span>
                    {status && (
                        <span className="text-xs text-muted-foreground">
                            （{status.count} 个 Cookie）
                        </span>
                    )}
                </div>
                <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={loadStatus} disabled={loading}>
                        <RefreshCw className="h-3.5 w-3.5" />
                    </Button>
                    {status && status.count > 0 && (
                        <Button variant="ghost" size="sm" onClick={handleClear} className="text-red-500 hover:text-red-600">
                            <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                    )}
                </div>
            </div>

            {/* Cookie 列表（脱敏展示） */}
            {status && status.cookies.length > 0 && (
                <div className="rounded-md border bg-muted/30 p-3 space-y-1 max-h-32 overflow-y-auto">
                    {status.cookies.map((c) => (
                        <div key={c.name} className="flex items-center gap-2 text-xs font-mono">
                            <span className="font-semibold text-foreground w-20 shrink-0">{c.name}</span>
                            <span className="text-muted-foreground truncate">{c.masked}</span>
                        </div>
                    ))}
                </div>
            )}

            {/* 从浏览器采集 */}
            <div className="flex items-center gap-2">
                <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCapture}
                    disabled={loading}
                    className="gap-1.5"
                >
                    <Globe className="h-3.5 w-3.5" />
                    从浏览器采集
                </Button>
                <span className="text-xs text-muted-foreground">需要先在浏览器中登录微博</span>
            </div>

            {/* 手动粘贴 */}
            <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">手动粘贴 Cookie</label>
                <textarea
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono resize-none h-20 focus:outline-none focus:ring-2 focus:ring-ring placeholder:text-muted-foreground"
                    placeholder="粘贴 document.cookie 内容，如：SUB=xxx; SUBP=xxx; XSRF-TOKEN=xxx"
                    value={rawCookie}
                    onChange={(e) => setRawCookie(e.target.value)}
                />
                <Button
                    size="sm"
                    onClick={handleSave}
                    disabled={!rawCookie.trim() || saving}
                    className="gap-1.5"
                >
                    {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                    保存 Cookie
                </Button>
            </div>
        </div>
    );
}
