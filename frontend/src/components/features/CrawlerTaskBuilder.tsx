"use client";

import * as React from "react";
import Link from "next/link";
import { MessageSquareText, Settings, TerminalSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { PostSearchTaskBuilder } from "@/components/features/PostSearchTaskBuilder";
import { CommentBackfillBuilder } from "@/components/features/CommentBackfillBuilder";

type BuilderMode = "search" | "comment_backfill";

const MODE_OPTIONS: Array<{
    value: BuilderMode;
    label: string;
    description: string;
}> = [
    {
        value: "search",
        label: "帖子采集",
        description: "常规关键词采集入口，可选直接抓评论。",
    },
    {
        value: "comment_backfill",
        label: "评论补采",
        description: "导入历史导出文件，只回补有评论的原帖。",
    },
];

export function CrawlerTaskBuilder() {
    const [mode, setMode] = React.useState<BuilderMode>("search");

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
                            先抓帖子，再按需要补评论。把一次性重任务拆成两条路径，降低主采集时的风险和等待成本。
                        </CardDescription>
                    </div>
                    <Link href="/settings" className="shrink-0">
                        <Button variant="outline" className="rounded-xl">
                            <Settings className="mr-2 h-4 w-4" />
                            打开设置
                        </Button>
                    </Link>
                </div>

                <div className="mt-5 grid gap-2 rounded-[1.25rem] border border-border/60 bg-background/60 p-2 sm:grid-cols-2">
                    {MODE_OPTIONS.map((option) => {
                        const active = mode === option.value;
                        return (
                            <button
                                key={option.value}
                                type="button"
                                onClick={() => setMode(option.value)}
                                className={cn(
                                    "rounded-2xl px-4 py-4 text-left transition-all duration-200",
                                    active ? "bg-primary/8 text-foreground shadow-sm ring-1 ring-primary/20" : "hover:bg-muted/50",
                                )}
                            >
                                <div className="flex items-center gap-2">
                                    {option.value === "comment_backfill" ? <MessageSquareText className="h-4 w-4 text-primary" /> : <TerminalSquare className="h-4 w-4 text-primary" />}
                                    <span className="font-medium">{option.label}</span>
                                </div>
                                <p className="mt-2 text-xs leading-5 text-muted-foreground">{option.description}</p>
                            </button>
                        );
                    })}
                </div>
            </CardHeader>

            <CardContent className="p-0">
                {mode === "search" ? <PostSearchTaskBuilder /> : <CommentBackfillBuilder />}
            </CardContent>
        </Card>
    );
}
