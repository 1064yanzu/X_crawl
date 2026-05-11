"use client";

import * as React from "react";
import Link from "next/link";
import { FileUp, MessageSquareText, Settings, TerminalSquare, Youtube } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { PostSearchTaskBuilder } from "@/components/features/PostSearchTaskBuilder";
import { CommentBackfillBuilder } from "@/components/features/CommentBackfillBuilder";
import { BatchImportBuilder } from "@/components/features/BatchImportBuilder";
import { YouTubeTaskBuilder } from "@/components/features/YouTubeTaskBuilder";

type BuilderMode = "search" | "comment_backfill" | "batch_import" | "youtube";

const MODE_ICONS: Record<BuilderMode, React.ElementType> = {
    search: TerminalSquare,
    comment_backfill: MessageSquareText,
    batch_import: FileUp,
    youtube: Youtube,
};

const MODE_OPTIONS: Array<{
    value: BuilderMode;
    label: string;
    description: string;
}> = [
    { value: "search", label: "帖子采集", description: "X / 微博 的关键词与时间范围。" },
    { value: "comment_backfill", label: "评论补采", description: "导入历史导出，回补有评论的原帖。" },
    { value: "batch_import", label: "批量导入", description: "批量关键词，顺序队列执行。" },
    { value: "youtube", label: "YouTube 采集", description: "官方 API · 关键词 / 频道 / 视频。" },
];

export function CrawlerTaskBuilder() {
    const [mode, setMode] = React.useState<BuilderMode>("search");

    return (
        <section aria-labelledby="task-builder-heading" className="space-y-6">
            <header className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-2">
                    <p className="font-mono text-[10.5px] uppercase tracking-[0.28em] text-[color:var(--fg-subtle)]">
                        Lead story · Task builder
                    </p>
                    <h2
                        id="task-builder-heading"
                        className="font-serif text-[1.95rem] font-medium leading-tight tracking-tight text-foreground"
                    >
                        新建一篇采集任务
                    </h2>
                    <p className="max-w-xl text-[13.5px] leading-7 text-[color:var(--fg-muted)]">
                        按平台与用途下笔：X / 微博 聚焦关键词与时间；YouTube 走官方 API；评论补采与批量导入服务历史复用。
                    </p>
                </div>
                <Link href="/settings" className="shrink-0">
                    <Button variant="outline">
                        <Settings className="mr-2 h-3.5 w-3.5" />
                        打开设置
                    </Button>
                </Link>
            </header>

            {/* Segmented tabs — 编辑感「目录」式切换：上下细线 + 文本 + active 下划线 */}
            <nav
                role="tablist"
                aria-label="任务类型"
                className="grid grid-cols-2 border-y border-[var(--line)] sm:grid-cols-4"
            >
                {MODE_OPTIONS.map((option, idx) => {
                    const active = mode === option.value;
                    const Icon = MODE_ICONS[option.value];
                    return (
                        <button
                            key={option.value}
                            type="button"
                            role="tab"
                            aria-selected={active}
                            onClick={() => setMode(option.value)}
                            className={cn(
 "group relative flex flex-col items-start gap-2 px-5 py-5 text-left",
 "transition-colors duration-200 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
                                idx !== 0 ? "sm:border-l sm:border-[var(--line)]" : "",
                                active
                                    ? "bg-[var(--surface-2)]/40 text-foreground"
                                    : "text-[color:var(--fg-muted)] hover:bg-[var(--surface-2)]/30 hover:text-foreground",
                            )}
                        >
                            <span
                                aria-hidden
                                className={cn(
 "absolute left-0 top-0 h-[2px] transition-all duration-300 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
                                    active ? "w-full bg-[var(--accent)]" : "w-0 bg-[var(--accent)]",
                                )}
                            />
                            <div className="flex items-center gap-2">
                                <span className="font-mono text-[9.5px] uppercase tracking-[0.22em] text-[color:var(--fg-subtle)]">
                                    {String(idx + 1).padStart(2, "0")}
                                </span>
                                <Icon className={cn("h-3.5 w-3.5", option.value === "youtube" ? "text-[var(--danger)]" : "text-[var(--accent)]")} />
                            </div>
                            <span className="font-serif text-[15px] tracking-tight">{option.label}</span>
                            <span className="text-[11.5px] leading-5 text-[color:var(--fg-subtle)]">{option.description}</span>
                        </button>
                    );
                })}
            </nav>

            <div className="pt-2">
                {mode === "search" && <PostSearchTaskBuilder />}
                {mode === "comment_backfill" && <CommentBackfillBuilder />}
                {mode === "batch_import" && <BatchImportBuilder />}
                {mode === "youtube" && <YouTubeTaskBuilder />}
            </div>
        </section>
    );
}
