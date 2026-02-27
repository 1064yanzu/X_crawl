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

    const set = (key: keyof typeof config) => (v: number) => setConfig((prev) => ({ ...prev, [key]: v }));

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
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Timer className="h-5 w-5 text-blue-500" /> 爬虫速率调优
                </CardTitle>
                <CardDescription>控制等待时序与恢复策略，所有配置均持久化生效。</CardDescription>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在读取配置...
                    </div>
                ) : (
                    <>
                        <div className="divide-y rounded-lg border bg-muted/10 px-4">
                            <ConfigRow label="数据包等待超时" description="等待 SearchTimeline/TweetDetail 包超时时间" value={config.crawler_timeout} onChange={set("crawler_timeout")} min={5} max={120} />
                            <ConfigRow label="翻页间隔" description="翻页间隔基线（会叠加抖动）" value={config.crawler_page_interval} onChange={set("crawler_page_interval")} min={1} max={60} />
                            <ConfigRow label="首次加载等待" description="搜索页首次加载后补充等待时间" value={config.crawler_initial_wait} onChange={set("crawler_initial_wait")} min={0} max={30} />
                            <ConfigRow label="评论区加载等待" description="评论页翻页后补充等待时间" value={config.crawler_reply_wait} onChange={set("crawler_reply_wait")} min={0} max={30} />
                            <ConfigRow label="实时预览条数" description="运行中任务详情页最大预览条数" value={config.crawler_preview_count} onChange={set("crawler_preview_count")} min={1} max={50} step={1} unit="条" />
                            <ConfigRow label="软重试次数" description="监听超时后的轻量恢复次数" value={config.crawler_packet_soft_retries} onChange={set("crawler_packet_soft_retries")} min={0} max={8} step={1} unit="次" />
                            <ConfigRow label="硬刷新次数" description="软重试失败后的硬刷新次数" value={config.crawler_refresh_max_retries} onChange={set("crawler_refresh_max_retries")} min={1} max={10} step={1} unit="次" />
                            <ConfigRow label="挑战页重试次数" description="风控挑战自动重试次数" value={config.crawler_challenge_retry_times} onChange={set("crawler_challenge_retry_times")} min={0} max={8} step={1} unit="次" />
                            <ConfigRow label="挑战页冷却时间" description="挑战页每次重试前冷却" value={config.crawler_challenge_cooldown} onChange={set("crawler_challenge_cooldown")} min={1} max={60} />
                            <ConfigRow label="并发任务上限" description="并发运行任务上限（调度器执行窗口）" value={config.crawler_max_concurrent_tasks} onChange={set("crawler_max_concurrent_tasks")} min={1} max={5} step={1} unit="个" />
                            <ConfigRow label="间隔下限" description="自适应等待启用时，翻页间隔下限" value={config.crawler_page_interval_min ?? 2.5} onChange={set("crawler_page_interval_min")} min={0.5} max={120} />
                            <ConfigRow label="间隔上限" description="自适应等待启用时，翻页间隔上限" value={config.crawler_page_interval_max ?? 8} onChange={set("crawler_page_interval_max")} min={0.5} max={180} />
                            <ConfigRow label="中断轮询粒度" description="长等待期间检查 pause/stop 的频率" value={config.crawler_interrupt_poll_ms ?? 300} onChange={set("crawler_interrupt_poll_ms")} min={50} max={3000} step={50} unit="ms" />
                            <ConfigRow label="检查点刷新间隔" description="DFS 回复阶段检查点最长刷新间隔" value={config.crawler_checkpoint_flush_interval_sec ?? 4} onChange={set("crawler_checkpoint_flush_interval_sec")} min={0.2} max={60} />
                            <ConfigRow label="检查点批次阈值" description="DFS 回复阶段每累计多少条触发检查点刷新" value={config.crawler_checkpoint_reply_batch ?? 3} onChange={set("crawler_checkpoint_reply_batch")} min={1} max={200} step={1} unit="条" />
                        </div>

                        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                            <label className="flex items-center justify-between rounded-lg border bg-muted/10 px-3 py-2 text-sm">
                                <span>自适应等待</span>
                                <input
                                    type="checkbox"
                                    checked={Boolean(config.crawler_adaptive_wait_enabled)}
                                    onChange={(e) => setConfig((prev) => ({ ...prev, crawler_adaptive_wait_enabled: e.target.checked }))}
                                />
                            </label>
                            <label className="flex items-center justify-between rounded-lg border bg-muted/10 px-3 py-2 text-sm" title="相同推文在不同关键词搜索中重复出现时，若互动数据未变化则跳过评论重复抓取">
                                <span>跨任务去重</span>
                                <input
                                    type="checkbox"
                                    checked={Boolean(config.crawler_dedup_enabled)}
                                    onChange={(e) => setConfig((prev) => ({ ...prev, crawler_dedup_enabled: e.target.checked }))}
                                />
                            </label>
                            <label className="flex items-center justify-between rounded-lg border bg-muted/10 px-3 py-2 text-sm">
                                <span>调度后端</span>
                                <select
                                    className="rounded border bg-background px-2 py-1 text-xs"
                                    value={config.scheduler_backend ?? "memory"}
                                    onChange={(e) => setConfig((prev) => ({ ...prev, scheduler_backend: e.target.value as "memory" | "redis" }))}
                                >
                                    <option value="memory">memory</option>
                                    <option value="redis">redis（预留）</option>
                                </select>
                            </label>
                        </div>

                        <div className="mt-4 flex items-center justify-between">
                            <p className="text-xs text-muted-foreground">推荐并发=1；极速模式建议翻页间隔 2~6 秒。</p>
                            <div className="flex items-center gap-2">
                                {isDirty && (
                                    <Button variant="ghost" size="sm" onClick={reset} className="h-8 text-xs text-muted-foreground">
                                        <RotateCcw className="mr-1 h-3 w-3" /> 撤销
                                    </Button>
                                )}
                                <Button size="sm" onClick={handleSave} disabled={saving || !isDirty} className={`h-8 min-w-[88px] text-xs ${saved ? "bg-emerald-600 hover:bg-emerald-600" : ""}`}>
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
