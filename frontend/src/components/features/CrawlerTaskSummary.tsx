import { Globe, Loader2, Play, Sparkles, Target } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function CrawlerTaskSummary({
    summaryRows,
    canSubmit,
    finalKeyword,
    selectedTabLabel,
    platformLabel,
    fetchReplies,
    loading,
    onSubmit,
}: {
    summaryRows: Array<{ label: string; value: string }>;
    canSubmit: boolean;
    finalKeyword: string;
    selectedTabLabel: string;
    platformLabel: string;
    fetchReplies: boolean;
    loading: boolean;
    onSubmit: () => void;
}) {
    return (
        <div className="space-y-4 xl:sticky xl:top-24">
            <div className="rounded-[1.25rem] border border-border/60 bg-card p-5 shadow-sm">
                <div className="flex items-center gap-2 text-primary">
                    <Sparkles className="h-4 w-4" />
                    <span className="text-xs font-semibold uppercase tracking-[0.18em]">Ready Check</span>
                </div>
                <h3 className="mt-3 text-lg font-semibold">提交前摘要</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    这里展示最终执行形态，帮助你在提交前快速检查平台、范围与成本。
                </p>

                <div className="mt-5 space-y-3">
                    {summaryRows.map((item) => (
                        <div key={item.label} className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-background/70 px-3 py-3 text-sm">
                            <span className="text-muted-foreground">{item.label}</span>
                            <span className="font-medium text-foreground">{item.value}</span>
                        </div>
                    ))}
                </div>

                <div className="mt-4 rounded-2xl border border-dashed border-border/70 bg-muted/20 p-4">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                        <Target className="h-3.5 w-3.5" />
                        最终查询
                    </div>
                    {canSubmit ? (
                        <code className="mt-3 block whitespace-pre-wrap break-words rounded-xl bg-background px-3 py-3 text-sm font-medium text-foreground">
                            {finalKeyword}
                        </code>
                    ) : (
                        <p className="mt-3 text-sm text-muted-foreground">输入关键词或高级筛选后，这里会显示最终提交到后端的查询。</p>
                    )}
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                    <Badge variant="secondary" className="h-7 rounded-full px-3">{selectedTabLabel}</Badge>
                    <Badge variant="secondary" className="h-7 rounded-full px-3">{platformLabel}</Badge>
                    {fetchReplies ? <Badge variant="secondary" className="h-7 rounded-full px-3">评论深抓</Badge> : null}
                </div>

                <Button onClick={onSubmit} disabled={!canSubmit || loading} className="mt-6 h-11 w-full rounded-xl">
                    {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                    {loading ? "提交中..." : "启动采集任务"}
                </Button>
            </div>

            <div className="rounded-[1.25rem] border border-border/60 bg-card p-5 shadow-sm">
                <div className="flex items-center gap-2 text-primary">
                    <Globe className="h-4 w-4" />
                    <span className="text-xs font-semibold uppercase tracking-[0.18em]">Tips</span>
                </div>
                <ul className="mt-3 space-y-3 text-sm leading-6 text-muted-foreground">
                    <li>默认推荐从“最新”开始，可更快验证关键词是否命中真实数据。</li>
                    <li>只有需要做传播分析或问答链路分析时，再开启评论抓取。</li>
                    <li>跨月或超长时间范围建议使用高级筛选里的日期条件，配合自动切片稳定运行。</li>
                </ul>
            </div>
        </div>
    );
}
