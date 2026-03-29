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
    const [backgroundTabs, setBackgroundTabs] = React.useState(false);
    const [foregroundOnLogin, setForegroundOnLogin] = React.useState(true);
    const [preferUserDataDir, setPreferUserDataDir] = React.useState(true);
    const [stealth, setStealth] = React.useState(true);
    const [linuxHardening, setLinuxHardening] = React.useState(true);
    const [autoCloseIdleBrowsers, setAutoCloseIdleBrowsers] = React.useState(true);
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
                setBackgroundTabs(Boolean(data.browser_background_tabs ?? false));
                setForegroundOnLogin(Boolean(data.browser_foreground_on_login ?? true));
                setPreferUserDataDir(Boolean(data.browser_prefer_user_data_dir ?? true));
                setStealth(Boolean(data.browser_stealth_enabled ?? true));
                setLinuxHardening(Boolean(data.browser_linux_hardening ?? true));
                setAutoCloseIdleBrowsers(Boolean(data.browser_pool_auto_close_idle ?? true));
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
                browser_background_tabs: backgroundTabs,
                browser_foreground_on_login: foregroundOnLogin,
                browser_prefer_user_data_dir: preferUserDataDir,
                browser_stealth_enabled: stealth,
                browser_linux_hardening: linuxHardening,
                browser_pool_auto_close_idle: autoCloseIdleBrowsers,
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
        <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl"><Cpu className="h-5 w-5" /> 爬虫引擎核心</CardTitle>
                <CardDescription>统一管理浏览器模式、实时推送和资源压力收敛策略。</CardDescription>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在读取引擎配置...
                    </div>
                ) : (
                    <div className="space-y-4">
                        <div className="grid gap-3 md:grid-cols-2">
                            <ToggleField label="无头模式" description="浏览器在后台静默运行，适合服务器环境。" checked={headless} onChange={setHeadless} disabled={saving} />
                            <ToggleField label="后台标签页" description="任务创建的新标签页保持在后台，减少前台打断。" checked={backgroundTabs} onChange={setBackgroundTabs} disabled={saving} />
                            <ToggleField label="登录时切回前台" description="遇到登录或风控时主动唤起浏览器，便于人工介入。" checked={foregroundOnLogin} onChange={setForegroundOnLogin} disabled={saving} />
                            <ToggleField label="优先复用用户目录" description="启动新浏览器时优先使用真实用户数据目录；若目录正被占用，会自动回退到隔离 Profile。" checked={preferUserDataDir} onChange={setPreferUserDataDir} disabled={saving} />
                            <ToggleField label="Stealth 伪装" description="增强浏览器伪装配置，优先提高平台兼容性。" checked={stealth} onChange={setStealth} disabled={saving} />
                            <ToggleField label="Linux 加固" description="针对 Linux 服务器启用更稳妥的浏览器运行参数。" checked={linuxHardening} onChange={setLinuxHardening} disabled={saving} />
                            <ToggleField label="空闲实例自动关闭" description="任务结束后自动关闭空闲浏览器实例，避免堆积多个可见窗口。" checked={autoCloseIdleBrowsers} onChange={setAutoCloseIdleBrowsers} disabled={saving} />
                            <ToggleField label="资源压力自动节流" description="内存或 CPU 逼近阈值时自动放慢翻页节奏。" checked={autoThrottle} onChange={setAutoThrottle} disabled={saving} />
                            <ToggleField label="动态并发收敛" description="资源压力高时自动降低有效并发上限。" checked={dynamicConcurrency} onChange={setDynamicConcurrency} disabled={saving} />
                        </div>

                        <div className="grid gap-3 md:grid-cols-3">
                            <NumberField
                                label="实时推送间隔"
                                description="详情页刷新频率，推荐 800ms。"
                                value={pushIntervalMs}
                                min={200}
                                max={5000}
                                step={50}
                                unit="ms"
                                onChange={setPushIntervalMs}
                                disabled={saving || loading}
                            />
                            <NumberField
                                label="内存告警阈值"
                                description="推荐 80%，临界值需高于它。"
                                value={memWarnPct}
                                min={50}
                                max={95}
                                step={1}
                                unit="%"
                                onChange={setMemWarnPct}
                                disabled={saving || loading}
                            />
                            <NumberField
                                label="内存临界阈值"
                                description="推荐 90%，超过后更强烈收敛。"
                                value={memCriticalPct}
                                min={55}
                                max={99}
                                step={1}
                                unit="%"
                                onChange={setMemCriticalPct}
                                disabled={saving || loading}
                            />
                        </div>

                        <div className="rounded-2xl border border-border/60 bg-muted/10 p-4 shadow-sm">
                            <p className="text-sm font-medium text-foreground">最大节流倍数</p>
                            <p className="mt-1 text-xs leading-5 text-muted-foreground">推荐值 3.0，范围 1.1 - 6.0，数值越高说明高压时减速越明显。</p>
                            <div className="mt-3 flex items-center gap-3">
                                <input
                                    type="number"
                                    min={1.1}
                                    max={6}
                                    step={0.1}
                                    value={throttleMaxFactor}
                                    onChange={(e) => setThrottleMaxFactor(Number(e.target.value) || 3)}
                                    disabled={saving || loading}
                                    className="h-11 w-32 rounded-xl border border-input bg-background px-3 font-mono text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                />
                                <span className="text-xs text-muted-foreground">倍</span>
                            </div>
                        </div>

                        <div className="flex justify-end rounded-[1.25rem] border border-border/60 bg-background/70 p-4 shadow-sm">
                            <Button size="sm" onClick={handleSave} disabled={saving || loading} className="min-w-[112px] rounded-xl">
                                {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
                                保存引擎设置
                            </Button>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

function ToggleField({
    label,
    description,
    checked,
    onChange,
    disabled,
}: {
    label: string;
    description: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
    disabled?: boolean;
}) {
    return (
        <label className="flex items-start justify-between gap-3 rounded-2xl border border-border/60 bg-muted/10 p-4 shadow-sm">
            <div>
                <p className="text-sm font-medium text-foreground">{label}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
            </div>
            <span className="relative mt-0.5 inline-flex cursor-pointer items-center">
                <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} disabled={disabled} />
                <span className="h-6 w-11 rounded-full bg-muted transition-colors peer-checked:bg-primary peer-disabled:opacity-50" />
                <span className="absolute left-[2px] top-[2px] h-5 w-5 rounded-full border bg-white transition-transform peer-checked:translate-x-full peer-disabled:opacity-50" />
            </span>
        </label>
    );
}

function NumberField({
    label,
    description,
    value,
    min,
    max,
    step,
    unit,
    onChange,
    disabled,
}: {
    label: string;
    description: string;
    value: number;
    min: number;
    max: number;
    step: number;
    unit: string;
    onChange: (value: number) => void;
    disabled?: boolean;
}) {
    return (
        <div className="rounded-2xl border border-border/60 bg-muted/10 p-4 shadow-sm">
            <p className="text-sm font-medium text-foreground">{label}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
            <div className="mt-3 flex items-center gap-2">
                <input
                    type="number"
                    min={min}
                    max={max}
                    step={step}
                    value={value}
                    onChange={(e) => onChange(Number(e.target.value) || min)}
                    disabled={disabled}
                    className="h-11 w-full rounded-xl border border-input bg-background px-3 font-mono text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <span className="text-xs text-muted-foreground">{unit}</span>
            </div>
        </div>
    );
}
