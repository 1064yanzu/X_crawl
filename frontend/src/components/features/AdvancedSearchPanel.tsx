"use client";

import { ChevronDown, SlidersHorizontal } from "lucide-react";
import {
    AccountsSection,
    DatesSection,
    EngagementSection,
    FilterSection,
    WordsSection,
} from "@/components/features/advanced-search/AdvancedSearchSections";
import { type AdvancedSearchParams, hasActiveFilters } from "@/lib/advanced-search";

interface Props {
    params: AdvancedSearchParams;
    onChange: (params: AdvancedSearchParams) => void;
    isOpen: boolean;
    onToggle: () => void;
}

function getActiveCount(params: AdvancedSearchParams) {
    return [
        params.allWords,
        params.exactPhrase,
        params.anyWords,
        params.noneWords,
        params.hashtags,
        params.lang,
        params.fromAccounts,
        params.toAccounts,
        params.mentionAccounts,
        params.replyFilter !== "off" ? "1" : "",
        params.linkFilter !== "off" ? "1" : "",
        params.minReplies,
        params.minFaves,
        params.minRetweets,
        params.since,
        params.until,
    ].filter(Boolean).length;
}

export function AdvancedSearchPanel({ params, onChange, isOpen, onToggle }: Props) {
    const update = (key: keyof AdvancedSearchParams, value: string) => {
        onChange({ ...params, [key]: value });
    };

    const activeCount = getActiveCount(params);
    const hasFilters = hasActiveFilters(params);

    return (
        <div className="rounded-md border border-border bg-card shadow-sm">
            <button
                type="button"
                onClick={onToggle}
                className="flex w-full items-center justify-between gap-3 rounded-md px-4 py-3 text-left transition-colors hover:bg-muted/30"
                aria-expanded={isOpen}
            >
                <div className="flex min-w-0 items-center gap-3">
                    <div className="rounded-md border border-border bg-background p-2 text-primary shadow-sm">
                        <SlidersHorizontal className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium text-foreground">高级搜索面板</p>
                            {hasFilters ? (
                                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                                    已启用 {activeCount} 项
                                </span>
                            ) : null}
                        </div>
                        <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
                            组合关键词、账号、互动量和时间范围，拼装更精确的 X 搜索查询。
                        </p>
                    </div>
                </div>
                <ChevronDown className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
            </button>

            {isOpen ? (
                <div className="border-t border-border px-4 py-4">
                    <div className="space-y-3 rounded-md border border-border bg-background p-4">
                        <WordsSection params={params} update={update} />
                        <AccountsSection params={params} update={update} />
                        <FilterSection
                            params={params}
                            onReplyChange={(value) => onChange({ ...params, replyFilter: value })}
                            onLinkChange={(value) => onChange({ ...params, linkFilter: value })}
                        />
                        <EngagementSection params={params} update={update} />
                        <DatesSection params={params} update={update} />
                    </div>
                </div>
            ) : null}
        </div>
    );
}
