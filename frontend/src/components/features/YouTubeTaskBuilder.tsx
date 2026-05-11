"use client";

import * as React from "react";
import Link from "next/link";
import { Hash, Link2, ListOrdered, MessageSquare, Youtube } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { YouTubeSource } from "@/services/api";
import { CrawlerTaskSummary } from "@/components/features/CrawlerTaskSummary";
import { SectionTitle } from "@/components/features/task-builder/TaskBuilderSection";
import { YouTubeKeywordFields } from "@/components/features/task-builder/youtube/KeywordFields";
import { YouTubeChannelFields } from "@/components/features/task-builder/youtube/ChannelFields";
import { YouTubeVideoUrlsFields } from "@/components/features/task-builder/youtube/VideoUrlsFields";
import { useYouTubeTaskBuilder } from "@/hooks/useYouTubeTaskBuilder";

type SourceTab = {
    value: YouTubeSource;
    label: string;
    hint: string;
    icon: React.ElementType;
};

const SOURCE_TABS: SourceTab[] = [
    {
        value: "keyword",
        label: "关键词搜索",
        hint: "search.list · 100 单位/次",
        icon: Hash,
    },
    {
        value: "channel",
        label: "频道视频列表",
        hint: "channels + playlistItems · 1 单位/次",
        icon: Link2,
    },
    {
        value: "video_urls",
        label: "视频链接批量",
        hint: "videos.list · 跳过搜索阶段",
        icon: ListOrdered,
    },
];

export function YouTubeTaskBuilder() {
    const builder = useYouTubeTaskBuilder();

    const sourceLabel =
        SOURCE_TABS.find((tab) => tab.value === builder.source)?.label ?? "关键词搜索";

    const finalKeyword =
        builder.source === "keyword"
            ? builder.keyword.trim() || "—"
            : builder.source === "channel"
              ? builder.channelInput.trim() || "—"
              : builder.parsedVideoIds.ids.length > 0
                ? `${builder.parsedVideoIds.ids.length} 个视频 · ${builder.parsedVideoIds.ids.slice(0, 3).join(", ")}${builder.parsedVideoIds.ids.length > 3 ? "..." : ""}`
                : "—";

    const videoCountValue =
        builder.source === "video_urls"
            ? `${builder.parsedVideoIds.ids.length} 个视频（由链接决定）`
            : `${builder.maxVideos} 个视频`;

    const summaryRows = [
        { label: "采集平台", value: "YouTube" },
        { label: "内容模式", value: sourceLabel },
        { label: "评论抓取", value: builder.fetchReplies ? `开启 · ${builder.replyDepth} 层` : "关闭" },
        { label: "采集规模", value: videoCountValue },
    ];

    return (
        <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-6 p-6 sm:p-7">
                <section className="space-y-4 rounded-lg border border-border bg-background p-5 shadow-sm">
                    <div className="flex items-start justify-between gap-3">
                        <SectionTitle
                            title="YouTube 采集"
                            description="通过 Google Data API v3 官方接口采集视频、频道和评论，不依赖浏览器。"
                        />
                        <Youtube className="h-5 w-5 text-red-600 dark:text-red-400" />
                    </div>
                    <p className="-mt-1 text-xs text-muted-foreground">
                        需要先在
                        <Link
                            href="/settings/youtube"
                            className="mx-1 underline underline-offset-4 hover:text-foreground"
                        >
                            设置 / YouTube
                        </Link>
                        配置至少一个 API Key，再创建任务。
                    </p>

                    <div className="grid grid-cols-1 gap-2 rounded-md border border-border bg-muted/20 p-1 sm:grid-cols-3">
                        {SOURCE_TABS.map((tab) => {
                            const Icon = tab.icon;
                            const active = builder.source === tab.value;
                            return (
                                <button
                                    key={tab.value}
                                    type="button"
                                    onClick={() => builder.setSource(tab.value)}
                                    className={cn(
 "rounded-md px-4 py-3 text-left transition-all",
                                        active
                                            ? "bg-background text-foreground shadow-sm ring-1 ring-primary/20"
                                            : "hover:bg-background",
                                    )}
                                >
                                    <div className="flex items-center gap-2 text-sm font-medium">
                                        <Icon className="h-4 w-4 text-primary" />
                                        {tab.label}
                                    </div>
                                    <p className="mt-1 text-xs text-muted-foreground">{tab.hint}</p>
                                </button>
                            );
                        })}
                    </div>
                </section>

                {builder.source === "keyword" && (
                    <YouTubeKeywordFields
                        keyword={builder.keyword}
                        onKeywordChange={builder.setKeyword}
                        type={builder.type}
                        onTypeChange={builder.setType}
                        order={builder.order}
                        onOrderChange={builder.setOrder}
                        regionCode={builder.regionCode}
                        onRegionCodeChange={builder.setRegionCode}
                        relevanceLanguage={builder.relevanceLanguage}
                        onRelevanceLanguageChange={builder.setRelevanceLanguage}
                        videoDuration={builder.videoDuration}
                        onVideoDurationChange={builder.setVideoDuration}
                        videoDefinition={builder.videoDefinition}
                        onVideoDefinitionChange={builder.setVideoDefinition}
                        startDate={builder.startDate}
                        onStartDateChange={builder.setStartDate}
                        endDate={builder.endDate}
                        onEndDateChange={builder.setEndDate}
                    />
                )}

                {builder.source === "channel" && (
                    <YouTubeChannelFields
                        channelInput={builder.channelInput}
                        onChannelInputChange={builder.setChannelInput}
                    />
                )}

                {builder.source === "video_urls" && (
                    <YouTubeVideoUrlsFields
                        text={builder.videoUrlsText}
                        onTextChange={builder.setVideoUrlsText}
                        fileName={builder.videoUrlsFileName}
                        onFileSelected={builder.onVideoUrlsFileSelected}
                        onClear={builder.clearVideoUrls}
                        parsed={builder.parsedVideoIds}
                    />
                )}

                {builder.source !== "video_urls" && (
                    <section className="space-y-4 rounded-lg border border-border bg-background p-5 shadow-sm">
                        <SectionTitle
                            title="采集规模"
                            description="每 50 个视频消耗 1 次 search.list（100 单位）+ 1 次 videos.list（1 单位）。"
                        />
                        <label className="flex flex-col gap-2 text-sm">
                            <span className="font-medium text-foreground">最大采集视频数</span>
                            <Input
                                type="number"
                                min={1}
                                max={500}
                                value={builder.maxVideos}
                                onChange={(event) =>
                                    builder.setMaxVideos(Number(event.target.value) || 0)
                                }
                                className="h-11 rounded-md"
                            />
                            <span className="text-xs text-muted-foreground">
                                抓评论会额外消耗 <code>1 + 评论分页数</code> 个配额/视频。
                            </span>
                        </label>
                    </section>
                )}

                <section className="space-y-4 rounded-lg border border-border bg-background p-5 shadow-sm">
                    <SectionTitle
                        title="评论抓取"
                        description="默认关闭。YouTube 评论需要独立 commentThreads.list 分页，会按视频数量翻倍消耗配额。"
                    />
                    <div className="rounded-md border border-border bg-muted/20 p-4">
                        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                            <div className="flex gap-3">
                                <div className="rounded-md bg-primary/10 p-2 text-primary">
                                    <MessageSquare className="h-4 w-4" />
                                </div>
                                <div>
                                    <p className="font-medium text-foreground">深入抓取评论回复</p>
                                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                                        开启后会对每个视频拉取顶层评论，若选择二级则再对每条评论分页拉取全部楼中楼。
                                    </p>
                                </div>
                            </div>
                            <button
                                type="button"
                                aria-pressed={builder.fetchReplies}
                                onClick={() => builder.setFetchReplies(!builder.fetchReplies)}
                                className={cn(
 "inline-flex h-11 shrink-0 whitespace-nowrap items-center rounded-full border px-4 text-sm font-medium transition-all",
                                    builder.fetchReplies
                                        ? "border-primary/20 bg-primary text-primary-foreground"
                                        : "border-border bg-background text-muted-foreground hover:text-foreground",
                                )}
                            >
                                {builder.fetchReplies ? "已开启" : "保持关闭"}
                            </button>
                        </div>

                        {builder.fetchReplies && (
                            <div className="mt-4 grid gap-3 border-t border-border pt-4 md:grid-cols-2">
                                {[
                                    { value: 1, title: "一级评论", description: "仅抓顶层评论。最快。" },
                                    { value: 2, title: "二级评论", description: "含每条评论的子回复，适合讨论网络分析。" },
                                ].map((option) => {
                                    const active = builder.replyDepth === option.value;
                                    return (
                                        <button
                                            key={option.value}
                                            type="button"
                                            onClick={() => builder.setReplyDepth(option.value)}
                                            className={cn(
 "rounded-md border px-4 py-4 text-left transition-all",
                                                active
                                                    ? "border-primary/30 bg-primary/8 text-foreground shadow-sm"
                                                    : "border-border bg-card hover:border-primary/20 hover:bg-muted/30",
                                            )}
                                        >
                                            <p className="font-medium">{option.title}</p>
                                            <p className="mt-2 text-xs leading-5 text-muted-foreground">
                                                {option.description}
                                            </p>
                                        </button>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </section>
            </div>

            <aside className="border-t border-border bg-muted/15 p-6 xl:border-l xl:border-t-0 xl:p-7">
                <CrawlerTaskSummary
                    summaryRows={summaryRows}
                    canSubmit={builder.canSubmit}
                    finalKeyword={finalKeyword}
                    selectedTabLabel={sourceLabel}
                    platformLabel="YouTube"
                    fetchReplies={builder.fetchReplies}
                    loading={builder.loading}
                    onSubmit={() => void builder.submit()}
                />
            </aside>
        </div>
    );
}
