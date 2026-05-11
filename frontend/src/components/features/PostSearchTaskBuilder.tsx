"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { CalendarRange, Clock, Film, Image, MessageSquare, Search, TrendingUp } from "lucide-react";
import { Input } from "@/components/ui/input";
import { CrawlerTaskSummary } from "@/components/features/CrawlerTaskSummary";
import { useCrawlerTaskBuilder } from "@/hooks/useCrawlerTaskBuilder";
import { useTaskQueueBuilder } from "@/hooks/useTaskQueueBuilder";
import { type AdvancedSearchParams } from "@/lib/advanced-search";
import { cn } from "@/lib/utils";
import { BuilderPanelSkeleton, PlatformButton, SectionTitle } from "@/components/features/task-builder/TaskBuilderSection";
import { TaskQueuePanel } from "@/components/features/task-builder/TaskQueuePanel";
import { TimeSplitControls } from "@/components/features/task-builder/TimeSplitControls";

const AdvancedSearchPanel = dynamic(
    () => import("@/components/features/AdvancedSearchPanel").then((module) => ({ default: module.AdvancedSearchPanel })),
    {
        loading: () => <BuilderPanelSkeleton title="高级筛选" />,
    },
);

const PRODUCT_TABS = [
    { value: "Top", label: "最热", desc: "按相关性与互动量", icon: TrendingUp },
    { value: "Latest", label: "最新", desc: "追踪实时动态", icon: Clock },
    { value: "Photos", label: "图片", desc: "聚焦图片内容", icon: Image },
    { value: "Videos", label: "视频", desc: "聚焦视频内容", icon: Film },
] as const;

type ProductType = (typeof PRODUCT_TABS)[number]["value"];

export function PostSearchTaskBuilder() {
    const {
        loading,
        keyword,
        setKeyword,
        product,
        setProduct,
        advancedParams,
        setAdvancedParams,
        advancedOpen,
        setAdvancedOpen,
        fetchReplies,
        setFetchReplies,
        replyDepth,
        setReplyDepth,
        platform,
        setPlatform,
        startDate,
        setStartDate,
        endDate,
        setEndDate,
        timeSplitMode,
        setTimeSplitMode,
        timeSplitWindowDays,
        setTimeSplitWindowDays,
        timeSplitMaxSegments,
        setTimeSplitMaxSegments,
        hasTaskTimeRange,
        xDefaultWindowDays,
        xDefaultMaxSegments,
        weiboDefaultWindowDays,
        weiboDefaultMaxSegments,
        finalKeyword,
        xSplitNotice,
        canSubmit,
        buildPayload,
        resetDraft,
        submit,
    } = useCrawlerTaskBuilder();

    const selectedTab = PRODUCT_TABS.find((item) => item.value === product) ?? PRODUCT_TABS[0];
    const platformLabel = platform === "x" ? "𝕏 Twitter" : "微博";
    const summaryRows = [
        { label: "采集平台", value: platformLabel },
        { label: "内容模式", value: selectedTab.label },
        { label: "评论抓取", value: fetchReplies ? `开启 · ${replyDepth} 层` : "关闭" },
        {
            label: "时间拆分",
            value: !hasTaskTimeRange
                ? "无时间范围"
                : timeSplitMode === "on"
                  ? `强制拆分 · ${timeSplitWindowDays} 天`
                  : timeSplitMode === "off"
                    ? "本次不拆分"
                    : "跟随默认",
        },
    ];
    const {
        queueName,
        setQueueName,
        drafts,
        submitting,
        addCurrentDraft,
        removeDraft,
        moveDraft,
        clearDrafts,
        submitQueue,
    } = useTaskQueueBuilder({ buildPayload, resetDraft });

    const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
            event.preventDefault();
            void submit();
        }
    };

    return (
        <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_300px] xl:gap-x-12">
            <div className="min-w-0 space-y-12 pb-2">
                <section className="space-y-5">
                    <SectionTitle
                        eyebrow="01 · Foundation"
                        title="基础信息"
                        description="先确定平台、关键词与基础采集目标。"
                    />
                    <div className="flex flex-col gap-0 sm:flex-row sm:gap-6">
                        <PlatformButton
                            active={platform === "x"}
                            label="𝕏 Twitter"
                            description="高级搜索 / 时间切片"
                            onClick={() => setPlatform("x")}
                        />
                        <PlatformButton
                            active={platform === "weibo"}
                            label="微博"
                            description="按日期范围批量回采"
                            onClick={() => setPlatform("weibo")}
                        />
                    </div>

                    <div className="space-y-2">
                        <label className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-[color:var(--fg-subtle)]">
                            目标关键词
                        </label>
                        <div className="relative">
                            <Search className="pointer-events-none absolute left-0 top-1/2 h-4 w-4 -translate-y-1/2 text-[color:var(--fg-subtle)]" />
                            <Input
                                value={keyword}
                                onChange={(event) => setKeyword(event.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="输入要追踪的话题、品牌、人物或事件"
                                className="pl-7"
                                autoFocus
                            />
                        </div>
                        <p className="text-[12px] leading-6 text-[color:var(--fg-muted)]">
                            {platform === "x"
                                ? "可直接输入关键词，也可仅通过下方高级搜索拼装查询；任务会持续抓取直到结果耗尽或被手动终止。"
                                : "微博仅使用此处关键词与日期范围；关键词按原样提交，如需兼容旧版 OR 自动拆分请在设置中开启。"}
                        </p>
                    </div>

                    {platform === "weibo" ? (
                        <div className="grid gap-5 sm:grid-cols-2">
                            <div className="space-y-2">
                                <label className="flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.22em] text-[color:var(--fg-subtle)]">
                                    <CalendarRange className="h-3.5 w-3.5" />
                                    开始日期
                                </label>
                                <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
                            </div>
                            <div className="space-y-2">
                                <label className="flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.22em] text-[color:var(--fg-subtle)]">
                                    <CalendarRange className="h-3.5 w-3.5" />
                                    结束日期
                                </label>
                                <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
                            </div>
                        </div>
                    ) : null}
                </section>

                <hr className="border-[var(--line)]" />

                <section className="space-y-5">
                    <SectionTitle
                        eyebrow="02 · Content"
                        title="内容策略"
                        description="选择最贴近业务目标的结果排序与内容类型。"
                    />
                    <div role="tablist" aria-label="内容策略" className="grid grid-cols-2 border-y border-[var(--line)] sm:grid-cols-4">
                        {PRODUCT_TABS.map(({ value, label, desc, icon: Icon }, idx) => {
                            const active = product === value;
                            return (
                                <button
                                    key={value}
                                    type="button"
                                    role="tab"
                                    aria-selected={active}
                                    onClick={() => setProduct(value as ProductType)}
                                    className={cn(
                                        "group relative flex min-w-0 flex-col items-start gap-1.5 px-4 py-4 text-left",
                                        "transition-colors duration-200 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
                                        idx !== 0 ? "sm:border-l sm:border-[var(--line)]" : "",
                                        idx === 2 ? "border-t border-[var(--line)] sm:border-t-0" : "",
                                        idx === 3 ? "border-t border-[var(--line)] sm:border-t-0" : "",
                                        active
                                            ? "text-foreground"
                                            : "text-[color:var(--fg-muted)] hover:text-foreground",
                                    )}
                                >
                                    <span
                                        aria-hidden
                                        className={cn(
                                            "absolute left-0 top-0 h-[2px] transition-all duration-300 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
                                            active ? "w-full bg-[var(--accent)]" : "w-0 bg-[var(--accent)]",
                                        )}
                                    />
                                    <div className="flex w-full items-center gap-2">
                                        <Icon className={cn("h-3.5 w-3.5 shrink-0", active ? "text-[var(--accent)]" : "text-[color:var(--fg-subtle)]")} />
                                        <span className="font-serif text-[14.5px] tracking-tight">{label}</span>
                                    </div>
                                    <p className="line-clamp-1 w-full text-[11.5px] leading-5 text-[color:var(--fg-subtle)]">{desc}</p>
                                </button>
                            );
                        })}
                    </div>
                </section>

                {platform === "x" ? (
                    <>
                        <hr className="border-[var(--line)]" />
                        <section className="space-y-5">
                            <SectionTitle
                                eyebrow="03 · Filter"
                                title="高级筛选"
                                description="需要时再展开，把复杂查询收纳到二级区域。"
                            />
                            <AdvancedSearchPanel
                                params={advancedParams}
                                onChange={setAdvancedParams as (params: AdvancedSearchParams) => void}
                                isOpen={advancedOpen}
                                onToggle={() => setAdvancedOpen((open) => !open)}
                            />
                            {xSplitNotice ? (
                                <div className="border-l-2 border-[var(--info)] bg-[color:var(--info-tint)]/60 px-4 py-3 text-[12.5px] leading-6 text-foreground">
                                    {xSplitNotice}
                                </div>
                            ) : null}
                        </section>
                    </>
                ) : null}

                <hr className="border-[var(--line)]" />

                <section className="space-y-5">
                    <SectionTitle
                        eyebrow={platform === "x" ? "04 · Slicing" : "03 · Slicing"}
                        title="时间拆分"
                        description="把拆分策略放到任务层，由你决定本次任务是否切段、怎么切。"
                    />
                    <TimeSplitControls
                        platform={platform}
                        hasTimeRange={hasTaskTimeRange}
                        mode={timeSplitMode}
                        windowDays={timeSplitWindowDays}
                        maxSegments={timeSplitMaxSegments}
                        onModeChange={setTimeSplitMode}
                        onWindowDaysChange={setTimeSplitWindowDays}
                        onMaxSegmentsChange={setTimeSplitMaxSegments}
                        defaultWindowDays={platform === "weibo" ? weiboDefaultWindowDays : xDefaultWindowDays}
                        defaultMaxSegments={platform === "weibo" ? weiboDefaultMaxSegments : xDefaultMaxSegments}
                    />
                </section>

                <hr className="border-[var(--line)]" />

                <section className="space-y-5">
                    <SectionTitle
                        eyebrow={platform === "x" ? "05 · Replies" : "04 · Replies"}
                        title="评论与扩展抓取"
                        description="默认关闭，只有确实需要评论层级时再开启。"
                    />
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div className="flex min-w-0 gap-3">
                            <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent)]" />
                            <div className="min-w-0">
                                <p className="font-serif text-[15px] tracking-tight text-foreground">深入抓取评论回复</p>
                                <p className="mt-1 text-[12.5px] leading-6 text-[color:var(--fg-muted)]">
                                    在搜索结果基础上进入推文详情抓取评论，显著增加耗时，适合舆情溯源与讨论网络分析。
                                </p>
                            </div>
                        </div>
                        <button
                            type="button"
                            aria-pressed={fetchReplies}
                            onClick={() => setFetchReplies((value) => !value)}
                            className={cn(
                                "inline-flex h-9 shrink-0 items-center whitespace-nowrap border px-4 font-mono text-[10.5px] uppercase tracking-[0.22em]",
                                "transition-colors duration-200 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
                                fetchReplies
                                    ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-contrast)]"
                                    : "border-[var(--line-strong)] text-[color:var(--fg-muted)] hover:text-foreground hover:border-[var(--fg-muted)]",
                            )}
                        >
                            {fetchReplies ? "已开启" : "保持关闭"}
                        </button>
                    </div>

                    {fetchReplies ? (
                        <div className="grid gap-0 border-y border-[var(--line)] md:grid-cols-2">
                            {[
                                { value: 1, title: "一级评论", description: "优先速度，仅采集推文直接评论。" },
                                { value: 2, title: "二级评论", description: "包含评论的子回复，更适合深度分析。" },
                            ].map((option, idx) => {
                                const active = replyDepth === option.value;
                                return (
                                    <button
                                        key={option.value}
                                        type="button"
                                        onClick={() => setReplyDepth(option.value)}
                                        className={cn(
                                            "group relative flex flex-col items-start gap-1.5 px-4 py-4 text-left",
                                            "transition-colors duration-200 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
                                            idx === 1 ? "border-t border-[var(--line)] md:border-t-0 md:border-l" : "",
                                            active ? "text-foreground" : "text-[color:var(--fg-muted)] hover:text-foreground",
                                        )}
                                    >
                                        <span
                                            aria-hidden
                                            className={cn(
                                                "absolute left-0 top-0 h-[2px] transition-all duration-300 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
                                                active ? "w-full bg-[var(--accent)]" : "w-0 bg-[var(--accent)]",
                                            )}
                                        />
                                        <p className="font-serif text-[14.5px] tracking-tight">{option.title}</p>
                                        <p className="text-[11.5px] leading-5 text-[color:var(--fg-subtle)]">{option.description}</p>
                                    </button>
                                );
                            })}
                        </div>
                    ) : null}
                </section>

                <hr className="border-[var(--line)]" />

                <TaskQueuePanel
                    queueName={queueName}
                    onQueueNameChange={setQueueName}
                    drafts={drafts}
                    onAddCurrent={addCurrentDraft}
                    onMove={moveDraft}
                    onRemove={removeDraft}
                    onClear={clearDrafts}
                    onSubmit={() => void submitQueue()}
                    submitting={submitting}
                />
            </div>

            <aside className="mt-12 min-w-0 border-t border-[var(--line)] pt-10 xl:mt-0 xl:border-l xl:border-t-0 xl:pl-12 xl:pt-0">
                <CrawlerTaskSummary
                    summaryRows={summaryRows}
                    canSubmit={canSubmit}
                    finalKeyword={finalKeyword}
                    selectedTabLabel={selectedTab.label}
                    platformLabel={platformLabel}
                    fetchReplies={fetchReplies}
                    loading={loading}
                    onSubmit={() => void submit()}
                />
            </aside>
        </div>
    );
}
