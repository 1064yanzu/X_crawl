"use client";
import * as React from "react";
import { Cpu, Loader2, Save } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/services/api";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";

export function EngineConfigCard() {
    const { push } = useToast();
    const [headless, setHeadless] = React.useState(false);
    const [stealth, setStealth] = React.useState(true);
    const [linuxHardening, setLinuxHardening] = React.useState(true);
    const [pushIntervalMs, setPushIntervalMs] = React.useState(800);
    const [autoThrottle, setAutoThrottle] = React.useState(true);
    const [dynamicConcurrency, setDynamicConcurrency] = React.useState(true);
    const [memWarnPct, setMemWarnPct] = React.useState(80);
    const [memCriticalPct, setMemCriticalPct] = React.useState(90);
    const [throttleMaxFactor, setThrottleMaxFactor] = React.useState(3);
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);

    React.useEffect(() => {
        api.crawlerConfig.get()
            .then((data) => {
                setHeadless(Boolean(data.browser_headless));
                setStealth(Boolean(data.browser_stealth_enabled ?? true));
                setLinuxHardening(Boolean(data.browser_linux_hardening ?? true));
                setPushIntervalMs(Number(data.crawler_live_push_interval_ms ?? 800));
                setAutoThrottle(Boolean(data.crawler_auto_throttle_enabled ?? true));
                setDynamicConcurrency(Boolean(data.crawler_dynamic_concurrency_enabled ?? true));
                setMemWarnPct(Number(data.crawler_memory_pressure_warn_pct ?? 80));
                setMemCriticalPct(Number(data.crawler_memory_pressure_critical_pct ?? 90));
                setThrottleMaxFactor(Number(data.crawler_resource_throttle_max_factor ?? 3));
            })
            .finally(() => setLoading(false));
    }, []);

    const handleSave = async () => {
        setSaving(true);
        try {
            const current = await api.crawlerConfig.get();
            await api.crawlerConfig.update({
                ...current,
                browser_headless: headless,
                browser_stealth_enabled: stealth,
                browser_linux_hardening: linuxHardening,
                crawler_live_push_interval_ms: Math.min(5000, Math.max(200, pushIntervalMs)),
                crawler_auto_throttle_enabled: autoThrottle,
                crawler_dynamic_concurrency_enabled: dynamicConcurrency,
                crawler_memory_pressure_warn_pct: Math.min(95, Math.max(50, memWarnPct)),
                crawler_memory_pressure_critical_pct: Math.min(99, Math.max(memWarnPct + 1, memCriticalPct)),
                crawler_resource_throttle_max_factor: Math.min(6, Math.max(1.1, throttleMaxFactor)),
            });
            push({ type: "success", title: "引擎配置已更新" });
        } catch (err) {
            push({ type: "error", title: "保存失败", description: err instanceof Error ? err.message : String(err) });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2"><Cpu className="h-5 w-5" /> 爬虫引擎核心</CardTitle>
                <CardDescription>配置无头运行、平衡档伪装与 Linux 服务器稳定性参数。</CardDescription>
            </CardHeader>
            <CardContent>
                <div className="space-y-3">
                    <div className="flex items-center justify-between rounded-lg border bg-muted/20 p-4">
                        <div>
                            <h4 className="font-medium">无头模式</h4>
                            <p className="text-sm text-muted-foreground">开启后浏览器在后台静默运行。</p>
                        </div>
                        {loading ? (
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        ) : (
                            <label className="relative inline-flex cursor-pointer items-center">
                                <input type="checkbox" className="peer sr-only" checked={headless} onChange={(e) => setHeadless(e.target.checked)} disabled={saving} />
                                <div className="h-6 w-11 rounded-full bg-muted peer-checked:bg-primary after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:bg-white after:transition-all peer-checked:after:translate-x-full" />
                            </label>
                        )}
                    </div>

                    <div className="flex items-center justify-between rounded-lg border bg-muted/20 p-4">
                        <div>
                            <h4 className="font-medium">Stealth 平衡档</h4>
                            <p className="text-sm text-muted-foreground">注入基础指纹修补（不伪造核心鉴权头）。</p>
                        </div>
                        <label className="relative inline-flex cursor-pointer items-center">
                            <input type="checkbox" className="peer sr-only" checked={stealth} onChange={(e) => setStealth(e.target.checked)} disabled={saving || loading} />
                            <div className="h-6 w-11 rounded-full bg-muted peer-checked:bg-primary after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:bg-white after:transition-all peer-checked:after:translate-x-full" />
                        </label>
                    </div>

                    <div className="flex items-center justify-between rounded-lg border bg-muted/20 p-4">
                        <div>
                            <h4 className="font-medium">Linux 无头加固</h4>
                            <p className="text-sm text-muted-foreground">自动补充 no-sandbox / dev-shm 等服务器稳定参数。</p>
                        </div>
                        <label className="relative inline-flex cursor-pointer items-center">
                            <input type="checkbox" className="peer sr-only" checked={linuxHardening} onChange={(e) => setLinuxHardening(e.target.checked)} disabled={saving || loading} />
                            <div className="h-6 w-11 rounded-full bg-muted peer-checked:bg-primary after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:bg-white after:transition-all peer-checked:after:translate-x-full" />
                        </label>
                    </div>

                    <div className="rounded-lg border bg-muted/20 p-4">
                        <h4 className="font-medium">实时推送间隔（ms）</h4>
                        <p className="text-sm text-muted-foreground mt-1">推荐 800ms，范围 200~5000。</p>
                        <input
                            type="number"
                            min={200}
                            max={5000}
                            step={50}
                            value={pushIntervalMs}
                            onChange={(e) => setPushIntervalMs(Number(e.target.value) || 800)}
                            disabled={saving || loading}
                            className="mt-3 w-full rounded-md border bg-background px-3 py-2 font-mono text-sm"
                        />
                    </div>

                    <div className="flex items-center justify-between rounded-lg border bg-muted/20 p-4">
                        <div>
                            <h4 className="font-medium">资源压力自动节流</h4>
                            <p className="text-sm text-muted-foreground">内存/CPU 逼近阈值时自动放慢翻页节奏，防止服务器卡死。</p>
                        </div>
                        <label className="relative inline-flex cursor-pointer items-center">
                            <input type="checkbox" className="peer sr-only" checked={autoThrottle} onChange={(e) => setAutoThrottle(e.target.checked)} disabled={saving || loading} />
                            <div className="h-6 w-11 rounded-full bg-muted peer-checked:bg-primary after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:bg-white after:transition-all peer-checked:after:translate-x-full" />
                        </label>
                    </div>

                    <div className="flex items-center justify-between rounded-lg border bg-muted/20 p-4">
                        <div>
                            <h4 className="font-medium">动态并发收敛</h4>
                            <p className="text-sm text-muted-foreground">资源压力高时自动降低有效并发上限（仅在并发大于 1 时生效）。</p>
                        </div>
                        <label className="relative inline-flex cursor-pointer items-center">
                            <input type="checkbox" className="peer sr-only" checked={dynamicConcurrency} onChange={(e) => setDynamicConcurrency(e.target.checked)} disabled={saving || loading} />
                            <div className="h-6 w-11 rounded-full bg-muted peer-checked:bg-primary after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:bg-white after:transition-all peer-checked:after:translate-x-full" />
                        </label>
                    </div>

                    <div className="rounded-lg border bg-muted/20 p-4">
                        <h4 className="font-medium">内存压力阈值（%）</h4>
                        <p className="text-sm text-muted-foreground mt-1">推荐 告警 80 / 临界 90。临界必须大于告警。</p>
                        <div className="mt-3 grid grid-cols-2 gap-3">
                            <input
                                type="number"
                                min={50}
                                max={95}
                                step={1}
                                value={memWarnPct}
                                onChange={(e) => setMemWarnPct(Number(e.target.value) || 80)}
                                disabled={saving || loading}
                                className="w-full rounded-md border bg-background px-3 py-2 font-mono text-sm"
                            />
                            <input
                                type="number"
                                min={55}
                                max={99}
                                step={1}
                                value={memCriticalPct}
                                onChange={(e) => setMemCriticalPct(Number(e.target.value) || 90)}
                                disabled={saving || loading}
                                className="w-full rounded-md border bg-background px-3 py-2 font-mono text-sm"
                            />
                        </div>
                    </div>

                    <div className="rounded-lg border bg-muted/20 p-4">
                        <h4 className="font-medium">最大节流倍数</h4>
                        <p className="text-sm text-muted-foreground mt-1">推荐 3.0，范围 1.1~6.0。</p>
                        <input
                            type="number"
                            min={1.1}
                            max={6}
                            step={0.1}
                            value={throttleMaxFactor}
                            onChange={(e) => setThrottleMaxFactor(Number(e.target.value) || 3)}
                            disabled={saving || loading}
                            className="mt-3 w-full rounded-md border bg-background px-3 py-2 font-mono text-sm"
                        />
                    </div>

                    <div className="flex justify-end">
                        <Button size="sm" onClick={handleSave} disabled={saving || loading} className="min-w-[112px]">
                            {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
                            保存引擎设置
                        </Button>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
