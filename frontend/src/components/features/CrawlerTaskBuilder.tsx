"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
    Clock,
    Film,
    Image,
    MessageSquare,
    Play,
    Search,
    Settings,
    Sparkles,
    Target,
    TerminalSquare,
    TrendingUp,
    Loader2,
    Globe,
    CalendarRange,
} from "lucide-react";
import { api, SearchRequest, CrawlStrategy, Platform } from "@/services/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import {
    AdvancedSearchPanel,
    AdvancedSearchParams,
    DEFAULT_ADVANCED_PARAMS,
    buildAdvancedQuery,
} from "@/components/features/AdvancedSearchPanel";

const PRODUCT_TABS = [
    { value: "Top", label: "最热", desc: "按相关性与互动量排序", icon: TrendingUp },
    { value: "Latest", label: "最新", desc: "用于追踪实时动态", icon: Clock },
    { value: "Photos", label: "图片", desc: "聚焦图片内容", icon: Image },
    { value: "Videos", label: "视频", desc: "聚焦视频内容", icon: Film },
] as const;

type ProductType = (typeof PRODUCT_TABS)[number]["value"];

export function CrawlerTaskBuilder() {
    const router = useRouter();
    const { push } = useToast();
    const [loading, setLoading] = React.useState(false);
    const [keyword, setKeyword] = React.useState("");
    const [maxCount, setMaxCount] = React.useState(0);
    const [product, setProduct] = React.useState<ProductType>("Top");
    const [advancedParams, setAdvancedParams] = React.useState<AdvancedSearchParams>(DEFAULT_ADVANCED_PARAMS);
    const [advancedOpen, setAdvancedOpen] = React.useState(false);
    const [fetchReplies, setFetchReplies] = React.useState(false);
    const strategy: CrawlStrategy = "dfs";
    const [replyDepth, setReplyDepth] = React.useState(2);
    const [platform, setPlatform] = React.useState<Platform>("x");
    const [startDate, setStartDate] = React.useState("");
    const [endDate, setEndDate] = React.useState("");
    const [splitTriggerDays, setSplitTriggerDays] = React.useState(30);

    React.useEffect(() => {
        api.crawlerConfig.get()
            .then((cfg) => setSplitTriggerDays(cfg.x_time_split_trigger_days ?? 30))
            .catch(() => undefined);
    }, []);

    const buildFinalKeyword = React.useCallback(() => {
        let query = keyword.trim();
        const advancedQuery = buildAdvancedQuery(advancedParams);
        if (advancedQuery) {
            query = query ? `${query} ${advancedQuery}` : advancedQuery;
        }
        return query;
    }, [advancedParams, keyword]);

    const finalKeyword = buildFinalKeyword();
    const canSubmit = Boolean(finalKeyword);
    const selectedTab = PRODUCT_TABS.find((item) => item.value === product) ?? PRODUCT_TABS[0];

    const xSplitNotice = React.useMemo(() => {
        if (platform !== "x" || !advancedParams.since || !advancedParams.until) return null;
        const start = new Date(`${advancedParams.since}T00:00:00`);
        const end = new Date(`${advancedParams.until}T00:00:00`);
        if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
        const days = Math.floor((end.getTime() - start.getTime()) / 86400000);
        if (days < splitTriggerDays) return null;
        if (days >= 90) {
            return `检测到 ${days} 天跨度，将自动按月拆分任务以提升稳定性。`;
        }
        return `检测到 ${days} 天跨度，将按时间窗口自动切片，提升覆盖率与稳定性。`;
    }, [advancedParams.since, advancedParams.until, platform, splitTriggerDays]);

    const submit = async () => {
        if (!finalKeyword) {
            push({ type: "error", title: "请输入检索关键词或高级筛选条件" });
            return;
        }
        if (platform === "weibo" && startDate && endDate && startDate > endDate) {
            push({ type: "error", title: "微博时间范围无效", description: "结束日期需要晚于开始日期。" });
            return;
        }

        setLoading(true);
        try {
            const payload: SearchRequest = {
                keyword: finalKeyword,
                max_count: maxCount,
                product,
                resume: true,
                fetch_replies: fetchReplies,
                max_replies_per_tweet: 0,
                reply_depth: replyDepth,
                crawl_strategy: strategy,
                platform,
                start_date: platform === "weibo" && startDate ? startDate : undefined,
                end_date: platform === "weibo" && endDate ? endDate : undefined,
            };
            const task = await api.search.create(payload);
            push({ type: "success", title: "采集任务已提交", description: "正在跳转到任务详情。" });
            router.push(`/tasks/${task.task_id}`);
        } catch (error) {
            console.error(error);
            const msg = error instanceof Error ? error.message : String(error);
            if (msg.includes("409")) {
                push({ type: "error", title: "当前并发任务已达上限", description: "请等待正在运行任务结束后再创建新任务。" });
            } else {
                push({ type: "error", title: "启动采集任务失败", description: msg });
            }
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
            event.preventDefault();
            void submit();
        }
    };

    const summaryRows = [
        { label: "采集平台", value: platform === "x" ? "𝕏 Twitter" : "微博" },
        { label: "内容模式", value: selectedTab.label },
        { label: "目标数量", value: maxCount > 0 ? `${maxCount} 条` : "不限数量" },
        { label: "评论抓取", value: fetchReplies ? `开启 · ${replyDepth} 层` : "关闭" },
    ];

    return (
        <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
            <CardHeader className="border-b border-border/50 pb-5">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                        <div className="mb-2 flex items-center gap-2 text-primary">
                            <TerminalSquare className="h-4 w-4" />
                            <span className="text-xs font-semibold uppercase tracking-[0.18em]">Task Builder</span>
                        </div>
                        <CardTitle className="text-2xl">新建采集任务</CardTitle>
                        <CardDescription className="mt-2 max-w-2xl leading-6">
                            保留单页操作效率，但把基础项、进阶筛选和风险较高选项分层展示，减少误操作与视觉噪音。
                        </CardDescription>
                    </div>
                    <Link href="/settings" className="shrink-0">
                        <Button variant="outline" className="rounded-xl">
                            <Settings className="mr-2 h-4 w-4" />
                            打开设置
                        </Button>
                    </Link>
                </div>
            </CardHeader>

            <CardContent className="p-0">
                <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_320px]">
                    <div className="space-y-6 p-6 sm:p-7">
                        <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
                            <SectionTitle title="基础信息" description="先确定平台、关键词与基础采集目标。" />

                            <div className="flex flex-wrap gap-2">
                                <PlatformButton
                                    active={platform === "x"}
                                    label="𝕏 Twitter"
                                    description="支持高级搜索与时间切片"
                                    onClick={() => setPlatform("x")}
                                />
                                <PlatformButton
                                    active={platform === "weibo"}
                                    label="微博"
                                    description="适合指定时间范围批量回采"
                                    onClick={() => setPlatform("weibo")}
                                />
                            </div>

                            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
                                <div className="space-y-2">
                                    <label className="text-sm font-medium text-foreground">目标关键词</label>
                                    <div className="relative">
                                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                        <Input
                                            value={keyword}
                                            onChange={(event) => setKeyword(event.target.value)}
                                            onKeyDown={handleKeyDown}
                                            placeholder="输入要追踪的话题、品牌、人物或事件"
                                            className="h-11 rounded-xl bg-background pl-10"
                                            autoFocus
                                        />
                                    </div>
                                    <p className="text-xs text-muted-foreground">可直接输入关键词，也可以只使用下方高级搜索拼装查询。</p>
                                </div>

                                <div className="space-y-2">
                                    <label htmlFor="max_count" className="text-sm font-medium text-foreground">目标采集数量</label>
                                    <Input
                                        id="max_count"
                                        type="number"
                                        min={0}
                                        step={1}
                                        value={maxCount}
                                        onChange={(event) => setMaxCount(Math.max(0, Number(event.target.value) || 0))}
                                        className="h-11 rounded-xl bg-background font-mono"
                                    />
                                    <p className="text-xs text-muted-foreground">输入 `0` 表示不限数量，持续抓取直到数据耗尽或手动终止。</p>
                                </div>
                            </div>

                            {platform === "weibo" ? (
                                <div className="grid gap-4 rounded-2xl border border-border/60 bg-muted/20 p-4 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <label className="flex items-center gap-2 text-sm font-medium">
                                            <CalendarRange className="h-4 w-4 text-primary" />
                                            开始日期
                                        </label>
                                        <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="h-11 rounded-xl bg-background" />
                                    </div>
                                    <div className="space-y-2">
                                        <label className="flex items-center gap-2 text-sm font-medium">
                                            <CalendarRange className="h-4 w-4 text-primary" />
                                            结束日期
                                        </label>
                                        <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="h-11 rounded-xl bg-background" />
                                    </div>
                                </div>
                            ) : null}
                        </section>

                        <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
                            <SectionTitle title="内容策略" description="选择最贴近业务目标的结果排序与内容类型。" />
                            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                                {PRODUCT_TABS.map(({ value, label, desc, icon: Icon }) => {
                                    const active = product === value;
                                    return (
                                        <button
                                            key={value}
                                            type="button"
                                            onClick={() => setProduct(value)}
                                            className={cn(
                                                "rounded-2xl border px-4 py-4 text-left transition-all duration-200",
                                                active
                                                    ? "border-primary/30 bg-primary/8 text-foreground shadow-sm"
                                                    : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
                                            )}
                                        >
                                            <div className="flex items-center gap-2">
                                                <div className={cn("rounded-xl p-2", active ? "bg-primary/12 text-primary" : "bg-muted text-muted-foreground")}>
                                                    <Icon className="h-4 w-4" />
                                                </div>
                                                <span className="font-medium">{label}</span>
                                            </div>
                                            <p className="mt-3 text-xs leading-5 text-muted-foreground">{desc}</p>
                                        </button>
                                    );
                                })}
                            </div>
                        </section>

                        {platform === "x" ? (
                            <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
                                <SectionTitle title="高级筛选" description="需要时再展开，把复杂查询收纳到二级区域。" />
                                <AdvancedSearchPanel
                                    params={advancedParams}
                                    onChange={setAdvancedParams}
                                    isOpen={advancedOpen}
                                    onToggle={() => setAdvancedOpen((open) => !open)}
                                />
                                {xSplitNotice ? (
                                    <div className="rounded-2xl border border-blue-200/70 bg-blue-50/70 px-4 py-3 text-sm text-blue-900 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-100">
                                        {xSplitNotice}
                                    </div>
                                ) : null}
                            </section>
                        ) : null}

                        <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
                            <SectionTitle title="评论与扩展抓取" description="默认关闭，只有确实需要评论层级时再开启。" />
                            <div className="rounded-2xl border border-border/60 bg-muted/20 p-4">
                                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                    <div className="flex gap-3">
                                        <div className="rounded-xl bg-primary/10 p-2 text-primary">
                                            <MessageSquare className="h-4 w-4" />
                                        </div>
                                        <div>
                                            <p className="font-medium text-foreground">深入抓取评论回复</p>
                                            <p className="mt-1 text-sm leading-6 text-muted-foreground">
                                                开启后会在搜索结果基础上进入推文详情抓取评论，显著增加耗时，但适合舆情溯源与讨论网络分析。
                                            </p>
                                        </div>
                                    </div>
                                    <button
                                        type="button"
                                        aria-pressed={fetchReplies}
                                        onClick={() => setFetchReplies((value) => !value)}
                                        className={cn(
                                            "inline-flex h-11 items-center rounded-full border px-4 text-sm font-medium transition-all",
                                            fetchReplies
                                                ? "border-primary/20 bg-primary text-primary-foreground"
                                                : "border-border/70 bg-background text-muted-foreground hover:text-foreground",
                                        )}
                                    >
                                        {fetchReplies ? "已开启" : "保持关闭"}
                                    </button>
                                </div>

                                {fetchReplies ? (
                                    <div className="mt-4 grid gap-3 border-t border-border/60 pt-4 md:grid-cols-2">
                                        {[
                                            { value: 1, title: "一级评论", description: "优先速度，仅采集推文直接评论。" },
                                            { value: 2, title: "二级评论", description: "包含评论的子回复，更适合深度分析。" },
                                        ].map((option) => {
                                            const active = replyDepth === option.value;
                                            return (
                                                <button
                                                    key={option.value}
                                                    type="button"
                                                    onClick={() => setReplyDepth(option.value)}
                                                    className={cn(
                                                        "rounded-2xl border px-4 py-4 text-left transition-all duration-200",
                                                        active
                                                            ? "border-primary/30 bg-primary/8 text-foreground shadow-sm"
                                                            : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
                                                    )}
                                                >
                                                    <p className="font-medium">{option.title}</p>
                                                    <p className="mt-2 text-xs leading-5 text-muted-foreground">{option.description}</p>
                                                </button>
                                            );
                                        })}
                                    </div>
                                ) : null}
                            </div>
                        </section>
                    </div>

                    <aside className="border-t border-border/50 bg-muted/15 p-6 xl:border-l xl:border-t-0 xl:p-7">
                        <div className="xl:sticky xl:top-24 space-y-4">
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
                                    <Badge variant="secondary" className="h-7 rounded-full px-3">{selectedTab.label}</Badge>
                                    <Badge variant="secondary" className="h-7 rounded-full px-3">{platform === "x" ? "X 平台" : "微博平台"}</Badge>
                                    {fetchReplies ? <Badge variant="secondary" className="h-7 rounded-full px-3">评论深抓</Badge> : null}
                                </div>

                                <Button onClick={() => void submit()} disabled={!canSubmit || loading} className="mt-6 h-11 w-full rounded-xl">
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
                    </aside>
                </div>
            </CardContent>
        </Card>
    );
}

function SectionTitle({ title, description }: { title: string; description: string }) {
    return (
        <div>
            <h3 className="text-base font-semibold text-foreground">{title}</h3>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>
        </div>
    );
}

function PlatformButton({
    active,
    label,
    description,
    onClick,
}: {
    active: boolean;
    label: string;
    description: string;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={cn(
                "min-w-[210px] rounded-2xl border px-4 py-3 text-left transition-all duration-200",
                active
                    ? "border-primary/30 bg-primary/8 text-foreground shadow-sm"
                    : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
            )}
        >
            <p className="font-medium">{label}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
        </button>
    );
}
