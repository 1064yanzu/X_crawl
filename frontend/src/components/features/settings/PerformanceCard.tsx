"use client";
import * as React from "react";
import { Brain, Database, Gauge, HardDrive, Loader2, RefreshCw, Save, Trash2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { api, MemoryStats, PerformanceConfig } from "@/services/api";
import { cn } from "@/lib/utils";

const STATS_POLL_INTERVAL_MS = 12_000;

export function PerformanceCard() {
    const { push } = useToast();
    const [config, setConfig] = React.useState<PerformanceConfig | null>(null);
    const [draft, setDraft] = React.useState<PerformanceConfig | null>(null);
    const [stats, setStats] = React.useState<MemoryStats | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);
    const [sweeping, setSweeping] = React.useState(false);

    const refreshAll = React.useCallback(async () => {
        try {
            const [cfg, mem] = await Promise.all([
                api.system.getPerformanceConfig(),
                api.system.memoryStats(),
            ]);
            setConfig(cfg);
            setDraft(cfg);
            setStats(mem);
        } catch (err) {
            push({
                type: "error",
                title: "无法加载性能配置",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setLoading(false);
        }
    }, [push]);

    const refreshStats = React.useCallback(async () => {
        try {
            setStats(await api.system.memoryStats());
        } catch { /* 静默忽略，下一次轮询继续 */ }
    }, []);

    React.useEffect(() => {
        void refreshAll();
        const tick = () => {
            if (document.visibilityState !== "visible") return;
            void refreshStats();
        };
        const timer = window.setInterval(tick, STATS_POLL_INTERVAL_MS);
        return () => window.clearInterval(timer);
    }, [refreshAll, refreshStats]);

    const dirty = React.useMemo(() => {
        if (!config || !draft) return false;
        return (Object.keys(config) as (keyof PerformanceConfig)[]).some((k) => config[k] !== draft[k]);
    }, [config, draft]);

    const setField = <K extends keyof PerformanceConfig>(key: K, value: PerformanceConfig[K]) => {
        setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
    };

    const handleSave = async () => {
        if (!draft) return;
        setSaving(true);
        try {
            const updated = await api.system.updatePerformanceConfig(draft);
            setConfig(updated);
            setDraft(updated);
            push({ type: "success", title: "性能配置已保存并立即生效" });
            void refreshStats();
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

    const handleSweep = async () => {
        setSweeping(true);
        try {
            const result = await api.rawResponses.sweep();
            push({
                type: "success",
                title: "归档清理完成",
                description: `删除 ${result.deleted_tasks} 个目录，释放 ${formatMB(result.freed_bytes)}，剩余 ${formatMB(result.remaining_bytes)}`,
            });
        } catch (err) {
            push({
                type: "error",
                title: "清理失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setSweeping(false);
        }
    };

    return (
        <Card className="rounded-lg border-border bg-card ">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                    <Gauge className="h-5 w-5 text-amber-500" /> 性能 · 内存 · 磁盘
                </CardTitle>
                <CardDescription>
                    决定单次最多在内存里「展开」几个任务的完整结果、归档目录怎么自动滚动清理、数据库 WAL 多久整理一次。改这里基本不会影响数据正确性，只影响占用。
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
                {loading || !draft ? (
                    <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在读取性能配置...
                    </div>
                ) : (
                    <>
                        <SectionHeading icon={Brain} label="任务结果缓存" />
                        <Row
                            label="LRU 条目上限"
                            description="同时在内存里保留多少个任务的完整结果。运行中/暂停的任务不会被淘汰；只挤掉最久未访问的终态任务。"
                            value={draft.crawler_result_cache_max_size}
                            min={4}
                            max={64}
                            step={1}
                            unit="个"
                            onChange={(v) => setField("crawler_result_cache_max_size", v)}
                        />
                        <Row
                            label="缓存内存上限"
                            description="LRU 估算占用超过该值即提前淘汰。粗估口径（每条推文 32KB），是上界保护，不是精确值。"
                            value={draft.crawler_result_cache_max_mb}
                            min={64}
                            max={4096}
                            step={64}
                            unit="MB"
                            onChange={(v) => setField("crawler_result_cache_max_mb", v)}
                        />

                        <SectionHeading icon={HardDrive} label="raw_responses 归档滚动清理" />
                        <ToggleRow
                            label="启用滚动清理"
                            description="关闭后只有手动或重启时才清理。后台守护线程默认每 30 分钟跑一次，仅删终态任务，绝不动正在写入的目录。"
                            checked={draft.raw_responses_cleanup_enabled}
                            onChange={(v) => setField("raw_responses_cleanup_enabled", v)}
                        />
                        <Row
                            label="清理执行间隔"
                            description="后台守护两次清理之间隔多久。"
                            value={draft.raw_responses_cleanup_interval_min}
                            min={5}
                            max={1440}
                            step={5}
                            unit="分钟"
                            onChange={(v) => setField("raw_responses_cleanup_interval_min", v)}
                        />
                        <Row
                            label="终态任务归档保留时长"
                            description="任务变成 done/stopped/failed 后，归档目录最多保留多久。"
                            value={draft.raw_responses_terminal_ttl_hours}
                            min={1}
                            max={720}
                            step={1}
                            unit="小时"
                            onChange={(v) => setField("raw_responses_terminal_ttl_hours", v)}
                        />
                        <Row
                            label="单任务归档上限"
                            description="任意终态任务归档超过该值，下一轮清理会整目录删除。"
                            value={draft.raw_responses_task_max_mb}
                            min={16}
                            max={10240}
                            step={16}
                            unit="MB"
                            onChange={(v) => setField("raw_responses_task_max_mb", v)}
                        />
                        <Row
                            label="全局归档上限"
                            description="所有归档总和超过该值时，按「最旧优先」删终态任务，直到回落。"
                            value={draft.raw_responses_global_max_gb}
                            min={0.5}
                            max={200}
                            step={0.5}
                            unit="GB"
                            onChange={(v) => setField("raw_responses_global_max_gb", v)}
                        />

                        <SectionHeading icon={Database} label="数据库维护" />
                        <Row
                            label="WAL checkpoint 周期"
                            description="周期性 PRAGMA wal_checkpoint(TRUNCATE)，回收 -wal 文件空间。设为 0 表示禁用（仅退出时执行一次）。"
                            value={draft.db_wal_checkpoint_interval_min}
                            min={0}
                            max={1440}
                            step={5}
                            unit="分钟"
                            onChange={(v) => setField("db_wal_checkpoint_interval_min", v)}
                        />

                        <div className="flex flex-col gap-3 rounded-lg border border-border bg-background p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                            <p className="text-xs text-muted-foreground">
                                清理与 WAL 配置保存后会立即生效，下一轮守护按新阈值执行。
                            </p>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={handleSweep}
                                    disabled={sweeping}
                                    className="rounded-md"
                                >
                                    {sweeping ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-1.5 h-3.5 w-3.5" />}
                                    立即清理一次
                                </Button>
                                <Button
                                    size="sm"
                                    onClick={handleSave}
                                    disabled={saving || !dirty}
                                    className="rounded-md"
                                >
                                    {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
                                    保存配置
                                </Button>
                            </div>
                        </div>

                        {stats ? (
                            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                                <StatItem
                                    label="LRU 占用"
                                    value={`${stats.lru_entries}/${stats.lru_max_size}`}
                                    hint={`约 ${stats.lru_estimated_mb} MB`}
                                />
                                <StatItem
                                    label="缓存推文总数"
                                    value={stats.lru_total_tweets.toLocaleString()}
                                />
                                <StatItem
                                    label="累计淘汰次数"
                                    value={stats.lru_evictions.toLocaleString()}
                                />
                                <StatItem
                                    label="后端 RSS"
                                    value={stats.process_rss_mb != null ? `${stats.process_rss_mb} MB` : "--"}
                                    hint={
                                        stats.scheduler_running != null
                                            ? `调度 ${stats.scheduler_running}/${stats.effective_worker_limit ?? "?"} · 排队 ${stats.scheduler_queue ?? 0}`
                                            : undefined
                                    }
                                />
                            </div>
                        ) : null}

                        <button
                            type="button"
                            onClick={() => { void refreshStats(); }}
                            className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-[color:var(--fg-muted)] underline-offset-[6px] transition-colors hover:text-[var(--accent)] hover:underline"
                        >
                            <RefreshCw className="mr-1 inline-block h-3 w-3" /> 刷新内存指标
                        </button>
                    </>
                )}
            </CardContent>
        </Card>
    );
}

function SectionHeading({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
    return (
        <div className="flex items-center gap-2 pt-2">
            <Icon className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-muted-foreground">
                {label}
            </span>
            <span className="h-px flex-1 bg-border" />
        </div>
    );
}

function Row({
    label,
    description,
    value,
    onChange,
    min,
    max,
    step,
    unit,
}: {
    label: string;
    description: string;
    value: number;
    onChange: (v: number) => void;
    min: number;
    max: number;
    step: number;
    unit: string;
}) {
    return (
        <div className="flex flex-col gap-3 rounded-md border border-border bg-background p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">{label}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
                <p className="mt-1 text-[11px] text-muted-foreground/80">范围 {min} – {max} {unit}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
                <input
                    type="number"
                    min={min}
                    max={max}
                    step={step}
                    value={value}
                    onChange={(e) => {
                        const next = parseFloat(e.target.value);
                        if (Number.isNaN(next)) return;
                        onChange(Math.max(min, Math.min(max, next)));
                    }}
                    className="h-11 w-28 rounded-md border border-input bg-background px-3 text-right font-mono text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <span className="min-w-12 text-xs text-muted-foreground">{unit}</span>
            </div>
        </div>
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

function StatItem({ label, value, hint }: { label: string; value: string; hint?: string }) {
    return (
        <div className={cn("rounded-md border border-border bg-muted/20 p-4 shadow-sm")}>
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="mt-1 text-base font-semibold text-foreground">{value}</p>
            {hint ? <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p> : null}
        </div>
    );
}

function formatMB(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}
