"use client";
import * as React from "react";
import { Check, Loader2, RotateCcw, Save, Timer } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useCrawlerConfig } from "@/hooks/useCrawlerConfig";
import { ConfigRow } from "./ConfigRow";
import { useToast } from "@/components/ui/toast";

export function CrawlerConfigCard() {
    const { loading, saving, config, setConfig, isDirty, save, reset } = useCrawlerConfig();
    const { push } = useToast();
    const [saved, setSaved] = React.useState(false);

    const set = (key: keyof typeof config) => (value: number) => setConfig((prev) => ({ ...prev, [key]: value }));

    const handleSave = async () => {
        try {
            await save();
            setSaved(true);
            push({ type: "success", title: "配置已应用" });
            setTimeout(() => setSaved(false), 1800);
        } catch (err) {
            push({ type: "error", title: "保存失败", description: err instanceof Error ? err.message : String(err) });
        }
    };

    return (
        <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                    <Timer className="h-5 w-5 text-blue-500" /> 爬虫速率调优
                </CardTitle>
                <CardDescription>控制等待时序与恢复策略，所有配置均会持久化生效。</CardDescription>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在读取配置...
                    </div>
                ) : (
                    <>
                        <div className="rounded-[1.25rem] border border-border/60 bg-muted/10 px-4 shadow-sm sm:px-5">
                            <ConfigRow label="数据包等待超时" description="等待 SearchTimeline / TweetDetail 包的最长时间。" value={config.crawler_timeout} onChange={set("crawler_timeout")} min={5} max={120} />
                            <ConfigRow label="翻页间隔" description="翻页的基线间隔，实际运行会叠加轻微抖动。" value={config.crawler_page_interval} onChange={set("crawler_page_interval")} min={1} max={60} />
                            <ConfigRow label="首次加载等待" description="搜索页首次加载完成后的补充等待时间。" value={config.crawler_initial_wait} onChange={set("crawler_initial_wait")} min={0} max={30} />
                            <ConfigRow label="评论区加载等待" description="评论页翻页后额外等待时间。" value={config.crawler_reply_wait} onChange={set("crawler_reply_wait")} min={0} max={30} />
                            <ConfigRow label="实时预览条数" description="任务详情中实时预览保留的最大条数。" value={config.crawler_preview_count} onChange={set("crawler_preview_count")} min={1} max={50} step={1} unit="条" />
                            <ConfigRow label="软重试次数" description="监听超时后的轻量恢复次数。" value={config.crawler_packet_soft_retries} onChange={set("crawler_packet_soft_retries")} min={0} max={8} step={1} unit="次" />
                            <ConfigRow label="硬刷新次数" description="软重试失败后执行整页刷新恢复的次数。" value={config.crawler_refresh_max_retries} onChange={set("crawler_refresh_max_retries")} min={1} max={10} step={1} unit="次" />
                            <ConfigRow label="挑战页重试次数" description="遇到风控挑战时自动重试的次数。" value={config.crawler_challenge_retry_times} onChange={set("crawler_challenge_retry_times")} min={0} max={8} step={1} unit="次" />
                            <ConfigRow label="挑战页冷却时间" description="每次风控重试前的冷却时间。" value={config.crawler_challenge_cooldown} onChange={set("crawler_challenge_cooldown")} min={1} max={60} />
                            <ConfigRow label="并发任务上限" description="调度器允许同时运行的任务数量。" value={config.crawler_max_concurrent_tasks} onChange={set("crawler_max_concurrent_tasks")} min={1} max={5} step={1} unit="个" />
                            <ConfigRow label="间隔下限" description="启用自适应等待时允许的最小翻页间隔。" value={config.crawler_page_interval_min ?? 2.5} onChange={set("crawler_page_interval_min")} min={0.5} max={120} />
                            <ConfigRow label="间隔上限" description="启用自适应等待时允许的最大翻页间隔。" value={config.crawler_page_interval_max ?? 8} onChange={set("crawler_page_interval_max")} min={0.5} max={180} />
                            <ConfigRow label="中断轮询粒度" description="长等待期间检查 pause / stop 的频率。" value={config.crawler_interrupt_poll_ms ?? 300} onChange={set("crawler_interrupt_poll_ms")} min={50} max={3000} step={50} unit="ms" />
                            <ConfigRow label="检查点刷新间隔" description="DFS 回复阶段检查点的最长刷新间隔。" value={config.crawler_checkpoint_flush_interval_sec ?? 4} onChange={set("crawler_checkpoint_flush_interval_sec")} min={0.2} max={60} />
                            <ConfigRow label="检查点批次阈值" description="累计多少条回复后强制刷新一次检查点。" value={config.crawler_checkpoint_reply_batch ?? 3} onChange={set("crawler_checkpoint_reply_batch")} min={1} max={200} step={1} unit="条" />
                            <ConfigRow label="X 时间分割触发阈值" description="时间跨度达到该天数后自动拆分搜索窗口。" value={config.x_time_split_trigger_days ?? 30} onChange={set("x_time_split_trigger_days")} min={1} max={3650} step={1} unit="天" />
                            <ConfigRow label="X 限定抓取窗口" description="跨度小于 90 天时的每段天数。" value={config.x_time_split_window_days ?? 14} onChange={set("x_time_split_window_days")} min={1} max={90} step={1} unit="天" />
                            <ConfigRow label="X 无限量窗口" description="无限量抓取时的每段天数。" value={config.x_time_split_window_days_unlimited ?? 7} onChange={set("x_time_split_window_days_unlimited")} min={1} max={30} step={1} unit="天" />
                            <ConfigRow label="X 最大分段数" description="自动时间切片允许生成的最大分段数。" value={config.x_time_split_max_segments ?? 120} onChange={set("x_time_split_max_segments")} min={1} max={500} step={1} unit="段" />
                        </div>

                        <div className="mt-4 grid gap-3 sm:grid-cols-2">
                            <ToggleField
                                label="自适应等待"
                                description="根据页面加载情况动态调整实际翻页间隔。"
                                checked={Boolean(config.crawler_adaptive_wait_enabled)}
                                onChange={(checked) => setConfig((prev) => ({ ...prev, crawler_adaptive_wait_enabled: checked }))}
                            />
                            <ToggleField
                                label="跨任务去重"
                                description="相同推文在不同关键词结果中重复出现时尽量跳过重复抓取。"
                                checked={Boolean(config.crawler_dedup_enabled)}
                                onChange={(checked) => setConfig((prev) => ({ ...prev, crawler_dedup_enabled: checked }))}
                            />
                            <ToggleField
                                label="X 自动时间分割"
                                description="跨度较大时自动拆分搜索窗口，提高稳定性。"
                                checked={Boolean(config.x_auto_time_split_enabled)}
                                onChange={(checked) => setConfig((prev) => ({ ...prev, x_auto_time_split_enabled: checked }))}
                            />
                            <div className="rounded-2xl border border-border/60 bg-muted/10 p-4 shadow-sm">
                                <div className="flex items-center justify-between gap-3">
                                    <div>
                                        <p className="text-sm font-medium text-foreground">调度后端</p>
                                        <p className="mt-1 text-xs leading-5 text-muted-foreground">当前默认使用内存调度，Redis 仅作为预留选项。</p>
                                    </div>
                                    <select
                                        className="h-10 rounded-xl border border-input bg-background px-3 text-xs shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                        value={config.scheduler_backend ?? "memory"}
                                        onChange={(e) => setConfig((prev) => ({ ...prev, scheduler_backend: e.target.value as "memory" | "redis" }))}
                                    >
                                        <option value="memory">memory</option>
                                        <option value="redis">redis（预留）</option>
                                    </select>
                                </div>
                            </div>
                        </div>

                        <div className="mt-4 flex flex-col gap-3 rounded-[1.25rem] border border-border/60 bg-background/70 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                            <p className="text-xs leading-5 text-muted-foreground">推荐并发为 1；极速模式建议将翻页间隔控制在 2 - 6 秒之间。</p>
                            <div className="flex items-center gap-2">
                                {isDirty ? (
                                    <Button variant="ghost" size="sm" onClick={reset} className="rounded-xl text-muted-foreground">
                                        <RotateCcw className="mr-1 h-3.5 w-3.5" /> 撤销
                                    </Button>
                                ) : null}
                                <Button size="sm" onClick={handleSave} disabled={saving || !isDirty} className={`min-w-[104px] rounded-xl ${saved ? "bg-emerald-600 hover:bg-emerald-600" : ""}`}>
                                    {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : saved ? <Check className="mr-1.5 h-3.5 w-3.5" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
                                    {saved ? "已保存" : "应用配置"}
                                </Button>
                            </div>
                        </div>
                    </>
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
}: {
    label: string;
    description: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
}) {
    return (
        <label className="flex items-start justify-between gap-3 rounded-2xl border border-border/60 bg-muted/10 p-4 shadow-sm">
            <div>
                <p className="text-sm font-medium text-foreground">{label}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
            </div>
            <span className="relative mt-0.5 inline-flex cursor-pointer items-center">
                <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
                <span className="h-6 w-11 rounded-full bg-muted transition-colors peer-checked:bg-primary" />
                <span className="absolute left-[2px] top-[2px] h-5 w-5 rounded-full border bg-white transition-transform peer-checked:translate-x-full" />
            </span>
        </label>
    );
}
