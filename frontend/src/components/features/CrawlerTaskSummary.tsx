import { Loader2, Play } from "lucide-react";
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
    const chips = [selectedTabLabel, platformLabel, fetchReplies ? "评论深抓" : null].filter(Boolean) as string[];

    return (
        <div className="space-y-10 xl:sticky xl:top-24">
            <section className="space-y-6">
                <header className="space-y-2">
                    <div className="flex items-center gap-3">
                        <span className="h-[2px] w-7 bg-[var(--accent)]" aria-hidden />
                        <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-[color:var(--fg-subtle)]">
                            Ready check
                        </p>
                    </div>
                    <h3 className="font-serif text-[1.45rem] font-medium leading-tight tracking-tight text-foreground">
                        提交前摘要
                    </h3>
                    <p className="max-w-[34ch] text-[12.5px] leading-6 text-[color:var(--fg-muted)]">
                        最终执行形态——平台、范围与成本一眼看清。
                    </p>
                </header>

                <dl className="divide-y divide-[var(--line)] border-y border-[var(--line)]">
                    {summaryRows.map((item) => (
                        <div key={item.label} className="flex items-baseline justify-between gap-3 py-3">
                            <dt className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-[color:var(--fg-subtle)]">
                                {item.label}
                            </dt>
                            <dd className="font-serif text-[14.5px] leading-snug text-foreground text-right">
                                {item.value}
                            </dd>
                        </div>
                    ))}
                </dl>

                <div className="space-y-2">
                    <p className="font-mono text-[10px] uppercase tracking-[0.26em] text-[color:var(--fg-subtle)]">
                        最终查询
                    </p>
                    {canSubmit ? (
                        <code className="block whitespace-pre-wrap break-words border-l-2 border-[var(--accent)] bg-[var(--surface-2)]/40 px-3 py-3 font-mono text-[12.5px] leading-6 text-foreground">
                            {finalKeyword}
                        </code>
                    ) : (
                        <p className="text-[12.5px] leading-6 text-[color:var(--fg-muted)]">
                            输入关键词或高级筛选后，这里会显示最终提交到后端的查询。
                        </p>
                    )}
                </div>

                {chips.length ? (
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 font-mono text-[10.5px] uppercase tracking-[0.2em] text-[color:var(--fg-muted)]">
                        {chips.map((chip, idx) => (
                            <span key={chip} className="flex items-center gap-3">
                                {idx > 0 ? <span aria-hidden className="h-3 w-px bg-[var(--line)]" /> : null}
                                <span>{chip}</span>
                            </span>
                        ))}
                    </div>
                ) : null}

                <Button onClick={onSubmit} disabled={!canSubmit || loading} className="w-full">
                    {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                    {loading ? "提交中…" : "启动采集任务"}
                </Button>
            </section>

            <section className="space-y-3">
                <div className="flex items-center gap-3">
                    <span className="h-px w-7 bg-[var(--line-strong)]" aria-hidden />
                    <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-[color:var(--fg-subtle)]">
                        Tips
                    </p>
                </div>
                <ul className="space-y-2.5 text-[12.5px] leading-6 text-[color:var(--fg-muted)]">
                    <li>默认推荐从「最新」开始，可更快验证关键词是否命中真实数据。</li>
                    <li>只有需要做传播分析或问答链路分析时，再开启评论抓取。</li>
                    <li>跨月或超长范围请在高级筛选里设置日期，并配合自动切片稳定运行。</li>
                </ul>
            </section>
        </div>
    );
}
