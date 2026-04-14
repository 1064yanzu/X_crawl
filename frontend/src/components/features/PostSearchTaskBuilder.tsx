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
    { value: "Top", label: "最热", desc: "按相关性与互动量排序", icon: TrendingUp },
    { value: "Latest", label: "最新", desc: "用于追踪实时动态", icon: Clock },
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
    const summaryRows = [
        { label: "采集平台", value: platform === "x" ? "𝕏 Twitter" : "微博" },
        { label: "内容模式", value: selectedTab.label },
        { label: "评论抓取", value: fetchReplies ? `开启 · ${replyDepth} 层` : "关闭" },
        { label: "时间拆分", value: !hasTaskTimeRange ? "无时间范围" : timeSplitMode === "on" ? `强制拆分 · ${timeSplitWindowDays} 天` : timeSplitMode === "off" ? "本次不拆分" : "跟随默认" },
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
        <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-6 p-6 sm:p-7">
                <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
                    <SectionTitle title="基础信息" description="先确定平台、关键词与基础采集目标。" />

                    <div className="flex flex-wrap gap-2">
                        <PlatformButton active={platform === "x"} label="𝕏 Twitter" description="支持高级搜索与时间切片" onClick={() => setPlatform("x")} />
                        <PlatformButton active={platform === "weibo"} label="微博" description="适合指定时间范围批量回采" onClick={() => setPlatform("weibo")} />
                    </div>

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
                        <p className="text-xs text-muted-foreground">
                            {platform === "x"
                                ? "可直接输入关键词，也可以只使用下方高级搜索拼装查询。任务会持续抓取直到当前结果耗尽或被你手动终止。"
                                : "微博仅使用这里的关键词与日期范围；关键词会按原样提交，如需兼容旧版 OR 自动拆分可在设置中开启。"}
                        </p>
                    </div>

                    {platform === "weibo" ? (
                        <div className="grid gap-4 rounded-2xl border border-border/60 bg-muted/20 p-4 md:grid-cols-2">
                            <div className="space-y-2">
                                <label className="flex items-center gap-2 text-sm font-medium">
                                    <CalendarRange className="h-4 w-4 text-primary" />开始日期
                                </label>
                                <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="h-11 rounded-xl bg-background" />
                            </div>
                            <div className="space-y-2">
                                <label className="flex items-center gap-2 text-sm font-medium">
                                    <CalendarRange className="h-4 w-4 text-primary" />结束日期
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
                                    onClick={() => setProduct(value as ProductType)}
                                    className={cn(
                                        "rounded-2xl border px-4 py-4 text-left transition-all duration-200",
                                        active ? "border-primary/30 bg-primary/8 text-foreground shadow-sm" : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
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
                            onChange={setAdvancedParams as (params: AdvancedSearchParams) => void}
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
                    <SectionTitle title="时间拆分" description="把拆分策略放到任务层，由你决定本次任务是否切段、怎么切。" />
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
                                    fetchReplies ? "border-primary/20 bg-primary text-primary-foreground" : "border-border/70 bg-background text-muted-foreground hover:text-foreground",
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
                                                active ? "border-primary/30 bg-primary/8 text-foreground shadow-sm" : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
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

            <aside className="border-t border-border/50 bg-muted/15 p-6 xl:border-l xl:border-t-0 xl:p-7">
                <CrawlerTaskSummary
                    summaryRows={summaryRows}
                    canSubmit={canSubmit}
                    finalKeyword={finalKeyword}
                    selectedTabLabel={selectedTab.label}
                    platformLabel={platform === "x" ? "X 平台" : "微博平台"}
                    fetchReplies={fetchReplies}
                    loading={loading}
                    onSubmit={() => void submit()}
                />
            </aside>
        </div>
    );
}
