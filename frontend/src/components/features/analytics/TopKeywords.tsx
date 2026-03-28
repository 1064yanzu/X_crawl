"use client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnalyticsOverview } from "@/services/api";

export function TopKeywords({
    data,
}: {
    data: AnalyticsOverview["top_keywords"];
}) {
    if (data.length === 0) {
        return (
            <Card className="rounded-2xl border-border/60 bg-card/90 shadow-sm backdrop-blur-sm">
                <CardHeader className="pb-3">
                    <CardTitle className="text-lg">关键词排行</CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="py-12 text-center text-sm text-muted-foreground">暂无数据</p>
                </CardContent>
            </Card>
        );
    }

    const maxTweets = Math.max(...data.map((d) => d.tweets), 1);

    return (
        <Card className="rounded-2xl border-border/60 bg-card/90 shadow-sm backdrop-blur-sm">
            <CardHeader className="pb-3">
                <CardTitle className="text-lg">关键词排行</CardTitle>
                <p className="text-xs text-muted-foreground">按推文数降序，前 20 名</p>
            </CardHeader>
            <CardContent>
                <div className="space-y-3">
                    {/* 表头 */}
                    <div className="grid grid-cols-[1fr_72px_72px_72px] gap-2 border-b border-border/60 pb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                        <span>关键词</span>
                        <span className="text-right">任务</span>
                        <span className="text-right">推文</span>
                        <span className="text-right">评论</span>
                    </div>

                    {data.map((item, idx) => (
                        <div key={item.keyword} className="group grid grid-cols-[1fr_72px_72px_72px] items-center gap-2">
                            <div className="min-w-0 space-y-1">
                                <div className="flex items-center gap-2">
                                    <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-muted text-[10px] font-bold text-muted-foreground">
                                        {idx + 1}
                                    </span>
                                    <span className="truncate text-sm font-medium text-foreground" title={item.keyword}>
                                        {item.keyword}
                                    </span>
                                </div>
                                {/* 进度条 */}
                                <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                                    <div
                                        className="h-full rounded-full bg-primary/60 transition-all duration-500"
                                        style={{ width: `${(item.tweets / maxTweets) * 100}%` }}
                                    />
                                </div>
                            </div>
                            <span className="text-right text-sm tabular-nums text-muted-foreground">
                                {item.tasks}
                            </span>
                            <span className="text-right text-sm font-medium tabular-nums text-foreground">
                                {item.tweets.toLocaleString()}
                            </span>
                            <span className="text-right text-sm tabular-nums text-muted-foreground">
                                {item.replies.toLocaleString()}
                            </span>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}
