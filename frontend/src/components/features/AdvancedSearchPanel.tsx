"use client";
import * as React from "react";
import { Input } from "@/components/ui/input";
import { ChevronDown, SlidersHorizontal } from "lucide-react";

export interface AdvancedSearchParams {
    lang: string;
    minFaves: string;
    minRetweets: string;
    since: string;
    until: string;
    exclude: string;
    exactPhrase: string;
}

interface Props {
    params: AdvancedSearchParams;
    onChange: (params: AdvancedSearchParams) => void;
    isOpen: boolean;
    onToggle: () => void;
}

export function AdvancedSearchPanel({ params, onChange, isOpen, onToggle }: Props) {
    const update = (key: keyof AdvancedSearchParams, value: string) => {
        onChange({ ...params, [key]: value });
    };

    return (
        <div className="border rounded-xl bg-card overflow-hidden transition-all duration-300">
            <button
                type="button"
                onClick={onToggle}
                className="w-full flex items-center justify-between p-4 bg-muted/20 hover:bg-muted/40 transition-colors"
            >
                <div className="flex items-center gap-2 font-medium text-sm text-foreground">
                    <SlidersHorizontal className="w-4 h-4 text-primary" />
                    高级筛选条件 (高级搜索)
                </div>
                <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`} />
            </button>

            <div className={`grid gap-4 transition-all duration-300 ease-in-out ${isOpen ? "grid-rows-[1fr] opacity-100 p-5 pt-2 border-t" : "grid-rows-[0fr] opacity-0"}`}>
                <div className="overflow-hidden space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <label htmlFor="lang" className="text-xs font-medium block">语言限定</label>
                            <select
                                id="lang"
                                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                                value={params.lang}
                                onChange={(e) => update("lang", e.target.value)}
                            >
                                <option value="">无限制 (Any)</option>
                                <option value="zh">中文 (Chinese)</option>
                                <option value="en">英文 (English)</option>
                                <option value="ja">日文 (Japanese)</option>
                                <option value="ko">韩文 (Korean)</option>
                            </select>
                        </div>
                        <div className="space-y-2">
                            <label htmlFor="exactPhrase" className="text-xs font-medium block">包含精确短语</label>
                            <Input
                                id="exactPhrase"
                                placeholder='如 "人工智能"将匹配完整短语'
                                value={params.exactPhrase}
                                onChange={(e) => update("exactPhrase", e.target.value)}
                                className="h-9"
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <label htmlFor="minFaves" className="text-xs font-medium block">最低点赞数</label>
                            <Input
                                id="minFaves"
                                type="number"
                                placeholder="如 1000"
                                value={params.minFaves}
                                onChange={(e) => update("minFaves", e.target.value)}
                                className="h-9"
                                min={0}
                            />
                        </div>
                        <div className="space-y-2">
                            <label htmlFor="minRetweets" className="text-xs font-medium block">最低转推数</label>
                            <Input
                                id="minRetweets"
                                type="number"
                                placeholder="如 500"
                                value={params.minRetweets}
                                onChange={(e) => update("minRetweets", e.target.value)}
                                className="h-9"
                                min={0}
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <label htmlFor="since" className="text-xs font-medium block">起始日期 (Since)</label>
                            <Input
                                id="since"
                                type="date"
                                value={params.since}
                                onChange={(e) => update("since", e.target.value)}
                                className="h-9"
                            />
                        </div>
                        <div className="space-y-2">
                            <label htmlFor="until" className="text-xs font-medium block">结束日期 (Until)</label>
                            <Input
                                id="until"
                                type="date"
                                value={params.until}
                                onChange={(e) => update("until", e.target.value)}
                                className="h-9"
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <label htmlFor="exclude" className="text-xs font-medium block">排除关键词 (空格分隔)</label>
                        <Input
                            id="exclude"
                            placeholder="如：推广 广告"
                            value={params.exclude}
                            onChange={(e) => update("exclude", e.target.value)}
                            className="h-9"
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}
