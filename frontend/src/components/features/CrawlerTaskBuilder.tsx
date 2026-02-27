"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, SearchRequest, CrawlStrategy } from "@/services/api";
import { Search, Sparkles, SlidersHorizontal, Play, Loader2, X, TerminalSquare, TrendingUp, Clock, Image, Film, Settings, MessageSquare, Layers, ArrowDown, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

type ProductType = "Top" | "Latest" | "Photos" | "Videos";

// Product tabs 配置 —— 与 X 搜索结果页面顺序一致
const PRODUCT_TABS: { value: ProductType; label: string; desc: string; icon: React.ElementType }[] = [
    { value: "Top", label: "最热", desc: "综合相关性 & 互动量排序", icon: TrendingUp },
    { value: "Latest", label: "最新", desc: "按发布时间倒序，实时推送", icon: Clock },
    { value: "Photos", label: "图片", desc: "仅含图片的推文", icon: Image },
    { value: "Videos", label: "视频", desc: "仅含视频的推文", icon: Film },
];

/**
 * Modern SaaS Scraping Task Builder
 */
export function CrawlerTaskBuilder() {
    const router = useRouter();
    const { push } = useToast();
    const [loading, setLoading] = React.useState(false);

    const [keyword, setKeyword] = React.useState("");
    const [maxCount, setMaxCount] = React.useState(0);
    const [product, setProduct] = React.useState<ProductType>("Top");
    const [filters, setFilters] = React.useState({
        lang: "",
        minFaves: "",
    });

    // 回复抓取选项
    const [fetchReplies, setFetchReplies] = React.useState(false);
    const [strategy, setStrategy] = React.useState<CrawlStrategy>("dfs");
    const [replyDepth, setReplyDepth] = React.useState(2);

    const buildFinalKeyword = () => {
        let q = keyword.trim();
        if (filters.lang) q += ` lang:${filters.lang}`;
        if (filters.minFaves) q += ` min_faves:${filters.minFaves}`;
        return q;
    };

    const handleSubmit = async (e?: React.FormEvent) => {
        if (e) e.preventDefault();
        if (!keyword.trim()) return;

        setLoading(true);
        try {
            const payload: SearchRequest = {
                keyword: buildFinalKeyword(),
                max_count: maxCount,
                product,
                resume: true,
                fetch_replies: fetchReplies,
                max_replies_per_tweet: 0, // 无限制
                reply_depth: replyDepth,
                crawl_strategy: strategy,
            };
            const task = await api.search.create(payload);
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

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") handleSubmit();
    };

    const selectedTab = PRODUCT_TABS.find(t => t.value === product)!;

    return (
        <div className="w-full bg-card border rounded-2xl shadow-sm overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b bg-muted/30 flex items-center justify-between">
                <div>
                    <h2 className="font-semibold text-lg flex items-center gap-2">
                        <TerminalSquare className="w-5 h-5 text-primary" />
                        新建采集任务
                    </h2>
                    <p className="text-sm text-muted-foreground mt-1">配置爬虫参数并将其投入后台运行队列</p>
                </div>
                <Link href="/settings" className="shrink-0">
                    <Button variant="outline" size="sm" className="h-8 gap-1.5 text-muted-foreground hover:text-foreground">
                        <Settings className="w-3.5 h-3.5" />
                        偏好设置
                    </Button>
                </Link>
            </div>

            <div className="p-6 flex flex-col gap-5">
                {/* Keyword Input */}
                <div className="space-y-2">
                    <label className="text-sm font-medium">目标关键词</label>
                    <div className="relative w-full flex items-center">
                        <div className="absolute left-3 text-muted-foreground shrink-0">
                            <Search className="w-4 h-4" />
                        </div>
                        <input
                            type="text"
                            value={keyword}
                            onChange={(e) => setKeyword(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="输入要采集的话题或关键字..."
                            className="flex-1 bg-background border border-input rounded-md h-10 pl-9 pr-4 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent w-full shadow-sm"
                            autoFocus
                        />
                    </div>
                </div>

                {/* Max Count */}
                <div className="space-y-2">
                    <label htmlFor="max_count" className="text-sm font-medium">目标采集数量（0 为不限制）</label>
                    <input
                        id="max_count"
                        type="number"
                        min={0}
                        step={1}
                        value={maxCount}
                        onChange={(e) => setMaxCount(Math.max(0, Number(e.target.value) || 0))}
                        placeholder="0 表示不限制，直到数据耗尽"
                        className="w-full bg-background border border-input rounded-md h-10 px-3 text-sm font-mono shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                    />
                </div>

                {/* ── 排序方式：分段控制器（仿 X 原生 tab 设计）── */}
                <div className="space-y-2">
                    <label className="text-sm font-medium flex items-center gap-1.5">
                        排序 / 内容类型
                        <span className="text-xs font-normal text-muted-foreground ml-1">— {selectedTab.desc}</span>
                    </label>

                    {/* 桌面端：4格横排 */}
                    <div className="grid grid-cols-4 gap-1 p-1 bg-muted/50 rounded-xl border border-border/30 hidden sm:grid">
                        {PRODUCT_TABS.map(({ value, label, icon: Icon }) => (
                            <button
                                key={value}
                                type="button"
                                onClick={() => setProduct(value)}
                                className={cn(
                                    "flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer",
                                    product === value
                                        ? "bg-background text-foreground shadow-sm border border-border/60"
                                        : "text-muted-foreground hover:text-foreground hover:bg-background/60"
                                )}
                            >
                                <Icon className="w-3.5 h-3.5 shrink-0" />
                                {label}
                                {value === "Latest" && (
                                    <span className="inline-flex items-center justify-center w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                                )}
                            </button>
                        ))}
                    </div>

                    {/* 移动端：select */}
                    <select
                        className="sm:hidden flex h-10 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={product}
                        onChange={(e) => setProduct(e.target.value as ProductType)}
                    >
                        {PRODUCT_TABS.map(({ value, label, desc }) => (
                            <option key={value} value={value}>{label} — {desc}</option>
                        ))}
                    </select>
                </div>

                {/* Filter Chips */}
                <div className="space-y-2">
                    <label className="text-sm font-medium flex items-center gap-1.5">
                        <SlidersHorizontal className="w-4 h-4 text-muted-foreground" />
                        附加过滤条件
                    </label>

                    <div className="flex flex-wrap items-center gap-2">
                        <button
                            type="button"
                            onClick={() => setFilters({ ...filters, lang: filters.lang === "zh" ? "" : "zh" })}
                            className={cn(
                                "px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200 border cursor-pointer flex items-center gap-1.5",
                                filters.lang === "zh"
                                    ? "bg-primary/10 border-primary text-primary shadow-sm"
                                    : "bg-background border-input hover:bg-muted text-muted-foreground"
                            )}
                        >
                            仅匹配中文 (lang:zh)
                            {filters.lang === "zh" && <X className="w-3 h-3" />}
                        </button>

                        <button
                            type="button"
                            onClick={() => setFilters({ ...filters, minFaves: filters.minFaves === "500" ? "" : "500" })}
                            className={cn(
                                "px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200 border cursor-pointer flex items-center gap-1.5",
                                filters.minFaves === "500"
                                    ? "bg-primary/10 border-primary text-primary shadow-sm"
                                    : "bg-background border-input hover:bg-muted text-muted-foreground"
                            )}
                        >
                            低质过滤 (min_faves:500)
                            {filters.minFaves === "500" && <X className="w-3 h-3" />}
                        </button>
                    </div>
                </div>

                {/* ── 回复抓取选项 ── */}
                <div className="space-y-3 pt-3 border-t">
                    <div className="flex items-start gap-3 p-4 rounded-xl border bg-muted/20 transition-colors">
                        <MessageSquare className="w-5 h-5 text-primary mt-0.5 shrink-0" />
                        <div className="flex-1 space-y-3">
                            <div className="flex items-center justify-between">
                                <div>
                                    <label htmlFor="fetch_replies" className="text-sm font-semibold cursor-pointer">
                                        深入抓取评论回复
                                    </label>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        开启后将在搜索完成后，自动提取每条推文详情里的全部评论（无上限，将显著增加耗时）
                                    </p>
                                </div>
                                <input
                                    type="checkbox"
                                    id="fetch_replies"
                                    className="rounded border-border text-primary focus:ring-primary w-4 h-4 cursor-pointer scale-110"
                                    checked={fetchReplies}
                                    onChange={(e) => setFetchReplies(e.target.checked)}
                                />
                            </div>

                            {fetchReplies && (
                                <div className="space-y-4 pt-4 border-t border-border/50 animate-in fade-in zoom-in-95 duration-200">
                                    {/* 评论抓取深度 */}
                                    <div className="space-y-2">
                                        <label className="text-xs font-medium text-muted-foreground">
                                            评论抓取深度
                                        </label>
                                        <div className="grid grid-cols-2 gap-2">
                                            {[
                                                { v: 1, l: "仅一级评论", d: "只抓取推文的直接评论" },
                                                { v: 2, l: "含二级评论", d: "抓取评论及其子评论（更耗时）" },
                                            ].map(opt => (
                                                <button
                                                    key={opt.v}
                                                    type="button"
                                                    onClick={() => setReplyDepth(opt.v)}
                                                    className={cn(
                                                        "flex flex-col items-start gap-1 p-3 rounded-xl border text-left cursor-pointer transition-all",
                                                        replyDepth === opt.v
                                                            ? "bg-primary/5 border-primary/50 text-foreground ring-1 ring-primary/20"
                                                            : "bg-background border-border text-muted-foreground hover:bg-muted/60"
                                                    )}
                                                >
                                                    <span className="font-semibold text-sm">{opt.l}</span>
                                                    <span className="text-[11px] leading-tight opacity-80">{opt.d}</span>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t bg-muted/10 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className={cn(
                    "text-xs flex items-center gap-2 text-muted-foreground transition-all duration-500",
                    keyword.trim() ? "opacity-100" : "opacity-0 pointer-events-none"
                )}>
                    <Sparkles className="w-4 h-4 text-primary shrink-0" />
                    <span className="truncate max-w-[200px] sm:max-w-xs">
                        编译指令: <code className="font-mono text-foreground font-semibold bg-muted px-1 py-0.5 rounded">{buildFinalKeyword()}</code>
                    </span>
                    <span className="ml-1 px-1.5 py-0.5 rounded bg-muted text-foreground/70 font-mono">
                        [{product}]
                    </span>
                </div>

                <Button
                    onClick={() => handleSubmit()}
                    disabled={!keyword.trim() || loading}
                    className="w-full sm:w-auto min-w-[140px]"
                >
                    {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
                    启动采集
                </Button>
            </div>
        </div>
    );
}
