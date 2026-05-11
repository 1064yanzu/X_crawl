import { ChevronLeft, ChevronRight, Database, Search } from "lucide-react";
import { LiveCrawlPreview } from "@/components/features/LiveCrawlPreview";
import { TweetCard } from "@/components/features/TweetCard";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { RESULT_FILTER_OPTIONS, type ResultDensity, type ResultFilter, type ResultSort, type TweetRecord } from "@/lib/task-results";
import { cn } from "@/lib/utils";
import type { TaskOut } from "@/services/api";

export function TaskResultsSection({
    task,
    active,
    exportReady,
    finishedTweets,
    filteredFinishedTweets,
    paginatedFinishedTweets,
    resultStats,
    resultQuery,
    onResultQueryChange,
    resultFilter,
    onResultFilterChange,
    resultSort,
    onResultSortChange,
    resultPageSize,
    onResultPageSizeChange,
    resultDensity,
    onResultDensityChange,
    visibleResultPage,
    totalResultPages,
    resultPageInput,
    onResultPageInputChange,
    onGoToResultPage,
    onResetFilters,
}: {
    task: TaskOut;
    active: boolean;
    exportReady: boolean;
    finishedTweets: TweetRecord[];
    filteredFinishedTweets: TweetRecord[];
    paginatedFinishedTweets: TweetRecord[];
    resultStats: { media: number; replies: number; links: number };
    resultQuery: string;
    onResultQueryChange: (value: string) => void;
    resultFilter: ResultFilter;
    onResultFilterChange: (value: ResultFilter) => void;
    resultSort: ResultSort;
    onResultSortChange: (value: ResultSort) => void;
    resultPageSize: number;
    onResultPageSizeChange: (value: number) => void;
    resultDensity: ResultDensity;
    onResultDensityChange: (value: ResultDensity) => void;
    visibleResultPage: number;
    totalResultPages: number;
    resultPageInput: string;
    onResultPageInputChange: (value: string) => void;
    onGoToResultPage: (page: number) => void;
    onResetFilters: () => void;
}) {
    return (
        <Card id="task-results" className="rounded-lg border-border bg-card p-5 shadow-sm sm:p-6">
            <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <h3 className="flex items-center gap-2 text-lg font-semibold">
                        <Database className="h-5 w-5 text-primary" />
                        {active ? "实时数据流" : "采集结果"}
                    </h3>
                    <p className="mt-1 text-sm text-muted-foreground">{active ? "任务仍在运行，下面展示实时预览。" : "任务已结束，下面展示最终结构化结果。"}</p>
                </div>
                {exportReady ? (
                    <div className="rounded-md border border-dashed border-border bg-background px-3 py-2 text-xs text-muted-foreground">
                        导出入口已收纳到顶部操作区；{active ? "任务运行中也可以先下载当前结果。" : "可直接下载 CSV 或 Excel 做复盘与分发。"}
                    </div>
                ) : null}
            </div>

            {active ? <LiveCrawlPreview task={task} /> : null}

            {!active ? (
                finishedTweets.length === 0 ? (
                    <EmptyState
                        icon={Database}
                        title="此次任务没有结构化结果"
                        description="可能未命中搜索条件，或任务在结构化输出前已经中止。"
                        className="py-20"
                    />
                ) : (
                    <div className="space-y-5">
                        <div className="rounded-lg border border-border bg-background p-4 shadow-sm">
                            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                <div className="space-y-3">
                                    <div>
                                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">结果检索</p>
                                        <p className="mt-1 text-sm text-foreground">共 {finishedTweets.length} 条结果，筛出 {filteredFinishedTweets.length} 条，当前第 {visibleResultPage} / {totalResultPages} 页</p>
                                    </div>
                                    <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                                        <span className="rounded-full bg-muted px-2.5 py-1">带媒体 {resultStats.media}</span>
                                        <span className="rounded-full bg-muted px-2.5 py-1">带回复 {resultStats.replies}</span>
                                        <span className="rounded-full bg-muted px-2.5 py-1">带外链 {resultStats.links}</span>
                                    </div>
                                </div>
                                <div className="grid w-full gap-3 xl:max-w-4xl xl:grid-cols-[minmax(0,1fr)_220px_160px_auto]">
                                    <div className="relative">
                                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                        <input
                                            type="text"
                                            value={resultQuery}
                                            onChange={(event) => onResultQueryChange(event.target.value)}
                                            placeholder="搜索正文、作者、用户名或标签"
                                            className="h-11 w-full rounded-md border border-input bg-background pl-10 pr-4 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                        />
                                    </div>
                                    <select
                                        value={resultSort}
                                        onChange={(event) => onResultSortChange(event.target.value as ResultSort)}
                                        className="h-11 rounded-md border border-border bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                    >
                                        <option value="newest">按发布时间（最新）</option>
                                        <option value="oldest">按发布时间（最早）</option>
                                        <option value="likes">按点赞数</option>
                                        <option value="engagement">按互动总量</option>
                                    </select>
                                    <select
                                        value={resultPageSize}
                                        onChange={(event) => onResultPageSizeChange(Number(event.target.value))}
                                        className="h-11 rounded-md border border-border bg-background px-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                    >
                                        <option value={10}>每页 10 条</option>
                                        <option value={20}>每页 20 条</option>
                                        <option value={50}>每页 50 条</option>
                                    </select>
                                    <div className="flex items-center gap-2 rounded-md border border-border bg-background p-1 shadow-sm">
                                        <Button type="button" variant={resultDensity === "comfortable" ? "default" : "ghost"} size="sm" className="rounded-lg" onClick={() => onResultDensityChange("comfortable")}>舒展阅读</Button>
                                        <Button type="button" variant={resultDensity === "compact" ? "default" : "ghost"} size="sm" className="rounded-lg" onClick={() => onResultDensityChange("compact")}>紧凑阅读</Button>
                                    </div>
                                </div>
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                                {RESULT_FILTER_OPTIONS.map((option) => (
                                    <Button
                                        key={option.value}
                                        variant="outline"
                                        size="sm"
                                        className={cn("rounded-full", resultFilter === option.value && "border-primary bg-primary/8 text-primary")}
                                        onClick={() => onResultFilterChange(option.value)}
                                    >
                                        {option.label}
                                    </Button>
                                ))}
                                {(resultQuery || resultFilter !== "all" || resultSort !== "newest") ? (
                                    <Button variant="ghost" size="sm" className="rounded-full" onClick={onResetFilters}>
                                        重置条件
                                    </Button>
                                ) : null}
                            </div>
                        </div>

                        {filteredFinishedTweets.length === 0 ? (
                            <EmptyState
                                icon={Search}
                                title="没有符合条件的结果"
                                description="可以修改搜索关键词、切换筛选方式，或恢复默认排序后再试一次。"
                                action={<Button variant="outline" className="rounded-md" onClick={onResetFilters}>恢复默认条件</Button>}
                            />
                        ) : (
                            <div className="space-y-4">
                                <div className="flex flex-col gap-3 rounded-lg border border-border bg-background px-4 py-3 text-sm text-muted-foreground shadow-sm lg:flex-row lg:items-center lg:justify-between">
                                    <div>
                                        当前页 <span className="font-medium text-foreground">{visibleResultPage}</span> / {totalResultPages}，每页 <span className="font-medium text-foreground">{resultPageSize}</span> 条。
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        <Button variant="outline" size="sm" className="rounded-md" onClick={() => onGoToResultPage(1)} disabled={visibleResultPage <= 1}>首页</Button>
                                        <Button variant="outline" size="sm" className="rounded-md" onClick={() => onGoToResultPage(visibleResultPage - 1)} disabled={visibleResultPage <= 1}>
                                            <ChevronLeft className="mr-1.5 h-3.5 w-3.5" />上一页
                                        </Button>
                                        <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
                                            <input
                                                type="number"
                                                min={1}
                                                max={totalResultPages}
                                                value={resultPageInput}
                                                onChange={(event) => onResultPageInputChange(event.target.value)}
                                                className="w-16 bg-transparent text-center text-sm focus:outline-none"
                                            />
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="rounded-lg px-2"
                                                onClick={() => {
                                                    const parsed = Number(resultPageInput);
                                                    if (Number.isFinite(parsed)) onGoToResultPage(parsed);
                                                }}
                                            >
                                                跳转
                                            </Button>
                                        </div>
                                        <Button variant="outline" size="sm" className="rounded-md" onClick={() => onGoToResultPage(visibleResultPage + 1)} disabled={visibleResultPage >= totalResultPages}>
                                            下一页<ChevronRight className="ml-1.5 h-3.5 w-3.5" />
                                        </Button>
                                        <Button variant="outline" size="sm" className="rounded-md" onClick={() => onGoToResultPage(totalResultPages)} disabled={visibleResultPage >= totalResultPages}>末页</Button>
                                    </div>
                                </div>
                                {paginatedFinishedTweets.map((tweet, index) => (
                                    <TweetCard
                                        key={`${(tweet.id as string) || task.task_id}-${visibleResultPage}-${index}`}
                                        tweet={tweet}
                                        compact={resultDensity === "compact"}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )
            ) : null}
        </Card>
    );
}
