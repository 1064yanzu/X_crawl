"use client";

import * as React from "react";
import { CalendarRange, Hash, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import type {
    YouTubeOrder,
    YouTubeType,
    YouTubeVideoDefinition,
    YouTubeVideoDuration,
} from "@/services/api";
import { SectionTitle } from "@/components/features/task-builder/TaskBuilderSection";
import { SelectField, type SelectFieldOption } from "./shared-fields";

const TYPE_OPTIONS: SelectFieldOption<YouTubeType>[] = [
    { value: "video", label: "视频" },
    { value: "channel", label: "频道" },
    { value: "playlist", label: "播放列表" },
];

const ORDER_OPTIONS: SelectFieldOption<YouTubeOrder>[] = [
    { value: "relevance", label: "相关性（默认）" },
    { value: "date", label: "最新发布" },
    { value: "viewCount", label: "观看最多" },
    { value: "rating", label: "评分最高" },
    { value: "title", label: "标题字母序" },
];

const DURATION_OPTIONS: SelectFieldOption<YouTubeVideoDuration>[] = [
    { value: "any", label: "不限" },
    { value: "short", label: "短视频（<4 分钟）" },
    { value: "medium", label: "中等（4–20 分钟）" },
    { value: "long", label: "长视频（>20 分钟）" },
];

const DEFINITION_OPTIONS: SelectFieldOption<YouTubeVideoDefinition>[] = [
    { value: "any", label: "不限清晰度" },
    { value: "high", label: "高清（HD）" },
    { value: "standard", label: "标清" },
];

interface Props {
    keyword: string;
    onKeywordChange: (value: string) => void;
    type: YouTubeType;
    onTypeChange: (value: YouTubeType) => void;
    order: YouTubeOrder;
    onOrderChange: (value: YouTubeOrder) => void;
    regionCode: string;
    onRegionCodeChange: (value: string) => void;
    relevanceLanguage: string;
    onRelevanceLanguageChange: (value: string) => void;
    videoDuration: YouTubeVideoDuration;
    onVideoDurationChange: (value: YouTubeVideoDuration) => void;
    videoDefinition: YouTubeVideoDefinition;
    onVideoDefinitionChange: (value: YouTubeVideoDefinition) => void;
    startDate: string;
    onStartDateChange: (value: string) => void;
    endDate: string;
    onEndDateChange: (value: string) => void;
}

export function YouTubeKeywordFields(props: Props) {
    return (
        <section className="space-y-5 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
            <SectionTitle
                title="关键词搜索"
                description="走官方 search.list，配额 100 单位/次。建议配合时间范围和最大视频数控制消耗。"
            />

            <label className="flex flex-col gap-1.5 text-sm">
                <span className="font-medium text-foreground flex items-center gap-1.5">
                    <Hash className="h-3.5 w-3.5" /> 搜索关键词
                </span>
                <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                        value={props.keyword}
                        onChange={(event) => props.onKeywordChange(event.target.value)}
                        placeholder="例如：claude code / machine learning / 机器学习"
                        className="h-11 rounded-xl pl-10"
                    />
                </div>
            </label>

            <div className="grid gap-3 md:grid-cols-2">
                <SelectField
                    label="资源类型"
                    value={props.type}
                    options={TYPE_OPTIONS}
                    onChange={props.onTypeChange}
                />
                <SelectField
                    label="排序方式"
                    value={props.order}
                    options={ORDER_OPTIONS}
                    onChange={props.onOrderChange}
                />
                <SelectField
                    label="视频时长"
                    value={props.videoDuration}
                    options={DURATION_OPTIONS}
                    onChange={props.onVideoDurationChange}
                />
                <SelectField
                    label="视频清晰度"
                    value={props.videoDefinition}
                    options={DEFINITION_OPTIONS}
                    onChange={props.onVideoDefinitionChange}
                />
                <label className="flex flex-col gap-1.5 text-sm">
                    <span className="font-medium text-foreground">内容地区（可选）</span>
                    <Input
                        value={props.regionCode}
                        onChange={(event) =>
                            props.onRegionCodeChange(event.target.value.toUpperCase().slice(0, 2))
                        }
                        placeholder="ISO 3166-1，如 US / CN / JP"
                        className="h-11 rounded-xl"
                    />
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                    <span className="font-medium text-foreground">相关语言（可选）</span>
                    <Input
                        value={props.relevanceLanguage}
                        onChange={(event) =>
                            props.onRelevanceLanguageChange(event.target.value.toLowerCase().slice(0, 5))
                        }
                        placeholder="BCP-47，如 zh / en / ja"
                        className="h-11 rounded-xl"
                    />
                </label>
            </div>

            <div className="grid gap-3 rounded-2xl border border-border/60 bg-muted/20 p-4 md:grid-cols-2">
                <div className="space-y-2">
                    <label className="flex items-center gap-2 text-sm font-medium">
                        <CalendarRange className="h-4 w-4 text-primary" /> 发布日期 起
                    </label>
                    <Input
                        type="date"
                        value={props.startDate}
                        onChange={(event) => props.onStartDateChange(event.target.value)}
                        className="h-11 rounded-xl bg-background"
                    />
                </div>
                <div className="space-y-2">
                    <label className="flex items-center gap-2 text-sm font-medium">
                        <CalendarRange className="h-4 w-4 text-primary" /> 发布日期 止
                    </label>
                    <Input
                        type="date"
                        value={props.endDate}
                        onChange={(event) => props.onEndDateChange(event.target.value)}
                        className="h-11 rounded-xl bg-background"
                    />
                </div>
                <p className="text-xs text-muted-foreground md:col-span-2">
                    留空即不限时间。仅对关键词搜索生效，频道与视频链接采集会忽略此项。
                </p>
            </div>
        </section>
    );
}
