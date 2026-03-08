"use client";
import * as React from "react";
import { Check, Globe, Loader2, Save } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/services/api";
import { useToast } from "@/components/ui/toast";

export function ProxyConfigCard() {
    const { push } = useToast();
    const [proxy, setProxy] = React.useState("");
    const [original, setOriginal] = React.useState("");
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);
    const [saved, setSaved] = React.useState(false);

    React.useEffect(() => {
        api.crawlerConfig.get()
            .then((data) => {
                const val = data.browser_proxy ?? "";
                setProxy(val);
                setOriginal(val);
            })
            .finally(() => setLoading(false));
    }, []);

    const isDirty = proxy !== original;

    const handleSave = async () => {
        setSaving(true);
        try {
            const current = await api.crawlerConfig.get();
            await api.crawlerConfig.update({ ...current, browser_proxy: proxy });
            setOriginal(proxy);
            setSaved(true);
            push({ type: "success", title: "代理配置已保存" });
            setTimeout(() => setSaved(false), 1800);
        } catch (err) {
            push({ type: "error", title: "保存失败", description: err instanceof Error ? err.message : String(err) });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
            <CardHeader>
                <CardTitle className="flex items-center gap-2"><Globe className="h-5 w-5" /> 网络与代理</CardTitle>
                <CardDescription>管理数据抓取过程的代理路由。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                <label className="text-sm font-medium">全局代理配置</label>
                {loading ? (
                    <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在读取...
                    </div>
                ) : (
                    <>
                        <input
                            type="text"
                            placeholder="http://127.0.0.1:7890"
                            className="h-11 w-full rounded-xl border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                            value={proxy}
                            onChange={(e) => setProxy(e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">留空表示使用默认出口 IP。</p>
                        {isDirty && (
                            <div className="flex justify-end">
                                <Button size="sm" onClick={handleSave} disabled={saving} className={`h-8 min-w-[80px] text-xs ${saved ? "bg-emerald-600 hover:bg-emerald-600" : ""}`}>
                                    {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : saved ? <Check className="mr-1.5 h-3.5 w-3.5" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
                                    {saved ? "已保存" : "保存代理"}
                                </Button>
                            </div>
                        )}
                    </>
                )}
            </CardContent>
        </Card>
    );
}

