"use client";
import * as React from "react";
import { Cpu, Layers, Loader2, RefreshCw, Save, Workflow } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { api, BrowserPoolStatus, CrawlerConfig } from "@/services/api";
import { cn } from "@/lib/utils";

const POOL_POLL_INTERVAL_MS = 8000;

export function ConcurrencyCard() {
    const { push } = useToast();
    const [config, setConfig] = React.useState<CrawlerConfig | null>(null);
    const [pool, setPool] = React.useState<BrowserPoolStatus | null>(null);
    const [draftMax, setDraftMax] = React.useState<number>(3);
    const [draftCross, setDraftCross] = React.useState<boolean>(true);
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);

    const refresh = React.useCallback(async () => {
        try {
            const [cfg, status] = await Promise.all([
                api.crawlerConfig.get(),
                api.browserPool.status(),
            ]);
            setConfig(cfg);
            setPool(status);
            setDraftMax(cfg.crawler_max_concurrent_tasks);
            setDraftCross(cfg.crawler_cross_platform_concurrent ?? true);
        } catch (err) {
            push({
                type: "error",
                title: "无法加载并发设置",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setLoading(false);
        }
    }, [push]);

    React.useEffect(() => {
        void refresh();
        const visible = () => document.visibilityState === "visible";
        const tick = () => {
            if (!visible()) return;
            api.browserPool.status().then(setPool).catch(() => {});
        };
        const timer = window.setInterval(tick, POOL_POLL_INTERVAL_MS);
        return () => window.clearInterval(timer);
    }, [refresh]);

    const dirty =
        config != null &&
        (draftMax !== config.crawler_max_concurrent_tasks ||
            draftCross !== (config.crawler_cross_platform_concurrent ?? true));

    const handleSave = async () => {
        if (!config) return;
        setSaving(true);
        try {
            const next = {
                ...config,
                crawler_max_concurrent_tasks: Math.max(1, Math.min(8, draftMax)),
                crawler_cross_platform_concurrent: draftCross,
            };
            const updated = await api.crawlerConfig.update(next);
            setConfig(updated);
            try {
                setPool(await api.browserPool.status());
            } catch { /* 忽略池状态拉取错误，不影响保存 */ }
            push({ type: "success", title: "并发设置已保存" });
        } catch (err) {
            push({
                type: "error",
                title: "保存失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Card className="rounded-lg border-border bg-card ">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                    <Workflow className="h-5 w-5 text-violet-500" /> 并发与调度
                </CardTitle>
                <CardDescription>
                    放开并发后，任务会在浏览器池里各拿一份独立实例同时跑；账号数不足时调度器会自动收敛上限，避免互相抢占 Cookie。
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
                {loading || !config ? (
                    <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在读取并发配置...
                    </div>
                ) : (
                    <>
                        <div className="space-y-4 rounded-lg border border-border bg-muted/20 p-4 shadow-sm">
                            <div className="flex flex-col gap-3 rounded-md border border-border bg-background p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                                <div>
                                    <p className="text-sm font-medium text-foreground">同时运行的任务数上限</p>
                                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                                        1 = 串行（旧行为），3 = 推荐起步，8 = 上限。每多一个并发会多一个 Chrome 进程；机器吃紧时调度器会自动降速。
                                    </p>
                                </div>
                                <div className="flex items-center gap-2">
                                    <input
                                        type="number"
                                        min={1}
                                        max={8}
                                        step={1}
                                        value={draftMax}
                                        onChange={(e) => setDraftMax(Math.max(1, Math.min(8, Number(e.target.value) || 1)))}
                                        className="h-11 w-24 rounded-md border border-input bg-background px-3 text-right font-mono text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                    />
                                    <span className="text-xs text-muted-foreground">个</span>
                                </div>
                            </div>

                            <ToggleRow
                                label="跨平台并发"
                                description="开启后 X、微博、YouTube 任务各自独享一份并发上限。关闭则退化为全局串行，更适合机器资源紧张时使用。"
                                checked={draftCross}
                                onChange={setDraftCross}
                            />

                            <div className="flex justify-end rounded-lg border border-border bg-background p-4 shadow-sm">
                                <Button
                                    size="sm"
                                    onClick={handleSave}
                                    disabled={saving || !dirty}
                                    className="rounded-md"
                                >
                                    {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
                                    保存并立即生效
                                </Button>
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                            <StatItem
                                icon={Layers}
                                label="实际并发上限"
                                value={pool ? String(pool.max_size) : "--"}
                                hint={pool ? `配置 ${pool.configured_max_size}` : undefined}
                            />
                            <StatItem
                                icon={Cpu}
                                label="X 有效上限"
                                value={pool ? String(pool.effective_x_concurrency_limit) : "--"}
                                hint={pool ? `${pool.active_x_accounts} 个可用账号` : undefined}
                            />
                            <StatItem
                                icon={Workflow}
                                label="占用槽位"
                                value={pool ? `${pool.active_slots}/${pool.total_slots}` : "--"}
                                hint={pool ? `空闲 ${pool.idle_slots}` : undefined}
                            />
                            <StatItem
                                icon={RefreshCw}
                                label="存活实例"
                                value={pool ? `${pool.alive_instances}/${pool.total_instances}` : "--"}
                                hint={pool ? `辅助 ${pool.aux_instances}` : undefined}
                            />
                        </div>
                    </>
                )}
            </CardContent>
        </Card>
    );
}

function ToggleRow({
    label,
    description,
    checked,
    onChange,
}: {
    label: string;
    description: string;
    checked: boolean;
    onChange: (v: boolean) => void;
}) {
    return (
        <label className="flex items-start justify-between gap-3 rounded-md border border-border bg-background p-4 shadow-sm">
            <div>
                <p className="text-sm font-medium text-foreground">{label}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
            </div>
            <span className="relative mt-0.5 inline-flex cursor-pointer items-center">
                <input
                    type="checkbox"
                    className="peer sr-only"
                    checked={checked}
                    onChange={(e) => onChange(e.target.checked)}
                />
                <span className="h-6 w-11 rounded-full bg-muted transition-colors peer-checked:bg-primary" />
                <span className="absolute left-[2px] top-[2px] h-5 w-5 rounded-full border bg-white transition-transform peer-checked:translate-x-full" />
            </span>
        </label>
    );
}

function StatItem({
    icon: Icon,
    label,
    value,
    hint,
}: {
    icon: React.ElementType;
    label: string;
    value: string;
    hint?: string;
}) {
    return (
        <div className={cn("rounded-md border border-border bg-muted/20 p-4 shadow-sm")}>
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                <Icon className="h-3.5 w-3.5" />
                {label}
            </div>
            <div className="mt-2 text-2xl font-semibold">{value}</div>
            {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
        </div>
    );
}
