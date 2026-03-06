"use client";
import * as React from "react";
import type { ReactNode } from "react";
import {
    Loader2, Pause, Database, Wifi, Code2, ScrollText,
    Zap, CheckCircle2, SplitSquareVertical,
} from "lucide-react";
import { TweetCard } from "@/components/features/TweetCard";
import { cn } from "@/lib/utils";
import { TaskOut } from "@/services/api";

interface LiveCrawlPreviewProps {
    task: TaskOut;
}

/**
 * 根据后端 crawl_phase 推断适合的图标
 */
function PhaseIcon({ phase, className }: { phase: string; className?: string }) {
    if (phase.includes("登录")) return <Wifi className={cn("w-4 h-4", className)} />;
    if (phase.includes("等待")) return <Loader2 className={cn("w-4 h-4 animate-spin", className)} />;
    if (phase.includes("解析") || phase.includes("完成")) return <CheckCircle2 className={cn("w-4 h-4", className)} />;
    if (phase.includes("脚本") || phase.includes("注入")) return <Code2 className={cn("w-4 h-4", className)} />;
    if (phase.includes("滚动") || phase.includes("翻页")) return <ScrollText className={cn("w-4 h-4", className)} />;
    return <Zap className={cn("w-4 h-4", className)} />;
}

/**
 * 爬取启动中的动画 Banner（无数据时）
 * 直接展示来自后端的 crawl_phase 精确状态
 */
function CrawlingEmptyState({ currentPage, crawlPhase }: {
    currentPage: number;
    crawlPhase: string;
}) {
    // 当后端有精确状态时展示，否则展示默认信息
    const displayPhase = crawlPhase || "正在连接目标节点...";

    return (
        <div className="flex flex-col items-center justify-center py-16 gap-6">
            {/* 核心动画：旋转圆环 + 脉冲 */}
            <div className="relative">
                <div className="w-16 h-16 rounded-full border-2 border-border animate-spin border-t-primary" />
                <div className="absolute inset-0 flex items-center justify-center">
                    <div className="w-8 h-8 rounded-full bg-primary/10 animate-pulse flex items-center justify-center">
                        <Database className="w-4 h-4 text-primary" />
                    </div>
                </div>
            </div>

            {/* 来自后端的精确阶段状态 */}
            <div className="flex flex-col items-center gap-2 max-w-sm text-center">
                <div
                    key={displayPhase}
                    className="flex items-center gap-2 animate-in fade-in slide-in-from-bottom-2 duration-500"
                >
                    <PhaseIcon phase={displayPhase} className="shrink-0 text-primary" />
                    <span className="text-sm font-medium text-foreground">{displayPhase}</span>
                </div>
                <p className="text-xs text-muted-foreground font-mono mt-1">
                    {currentPage > 0
                        ? `已完成第 ${currentPage} 页 · 等待下一批数据...`
                        : "Initializing crawler · Awaiting response chunks..."}
                </p>
            </div>

            {/* 底部提示 */}
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground/60 mt-2">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                <span>数据到达后将实时显示在下方，请稍候...</span>
            </div>
        </div>
    );
}

/**
 * 暂停状态 Banner
 */
function PausedBanner({ resultCount }: { resultCount: number }) {
    return (
        <div className="flex items-center justify-center py-10 gap-4">
            <div className="w-12 h-12 rounded-full bg-amber-500/10 flex items-center justify-center">
                <Pause className="w-6 h-6 text-amber-500" />
            </div>
            <div>
                <p className="font-semibold text-foreground">爬虫已暂停</p>
                <p className="text-sm text-muted-foreground mt-0.5">
                    {resultCount > 0
                        ? `已保留 ${resultCount} 条数据，点击「继续」恢复抓取`
                        : "点击「继续」恢复抓取"}
                </p>
            </div>
        </div>
    );
}

/**
 * 紧凑的实时状态横幅（有数据时在顶部展示）
 */
function LiveStatusBanner({
    task,
    previewCount,
}: {
    task: TaskOut;
    previewCount: number;
}) {
    const isRunning: boolean = task.status === "running" || task.status === "pending";
    const displayPhase = typeof task.crawl_phase === "string" ? task.crawl_phase : "";
    const latestActionType = typeof task.latest_action?.type === "string" ? task.latest_action.type : "";
    const phaseNode =
        isRunning && displayPhase.trim().length > 0 ? (
            <p
                key={`phase-${displayPhase}`}
                className="text-xs text-muted-foreground mt-1 font-mono animate-in fade-in duration-300"
            >
                {displayPhase}
            </p>
        ) : null;

    return (
        <div
            className={cn(
                "flex items-start gap-3 px-4 py-3 rounded-xl border text-sm mb-4",
                isRunning
                    ? "bg-blue-500/5 border-blue-500/20 text-blue-700 dark:text-blue-400"
                    : "bg-amber-500/5 border-amber-500/20 text-amber-700 dark:text-amber-400"
            )}
        >
            {isRunning ? (
                <Loader2 className="w-4 h-4 shrink-0 animate-spin mt-0.5" />
            ) : (
                <Pause className="w-4 h-4 shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium">
                        {isRunning ? "实时抓取中" : "已暂停"}
                    </span>
                    <span className="text-muted-foreground">
                        · 已获取{" "}
                        <span className="font-semibold text-foreground">{task.result_count}</span>{" "}
                        条，预览最新{" "}
                        <span className="font-semibold text-foreground">{previewCount}</span> 条
                    </span>
                    {task.result_count > 0 && task.max_count > 0 && isRunning && (
                        <span className="text-xs font-mono text-muted-foreground ml-auto">
                            {Math.round((task.result_count / task.max_count) * 100)}%
                        </span>
                    )}
                </div>
                {/* 精确阶段状态（来自后端） */}
                {phaseNode as unknown as ReactNode}
                {latestActionType ? (
                    <p className="text-[11px] text-muted-foreground mt-1">
                        最近动作: <span className="font-mono">{latestActionType}</span>
                    </p>
                ) : null}
                {typeof task.time_coverage?.combined_start_at === "string" && typeof task.time_coverage?.combined_end_at === "string" && (
                    <p className="text-[11px] text-muted-foreground mt-1">
                        覆盖时间: <span className="font-mono">{new Date(task.time_coverage.combined_start_at).toLocaleDateString()} ~ {new Date(task.time_coverage.combined_end_at).toLocaleDateString()}</span>
                    </p>
                )}
                {task.segment_progress?.enabled && (task.segment_progress.total_segments ?? 0) > 1 ? (
                    <p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
                        <SplitSquareVertical className="h-3 w-3" />
                        时间分段: {task.segment_progress.completed_segments}/{task.segment_progress.total_segments}
                        {task.segment_progress.current_since && task.segment_progress.current_until
                            ? ` · ${task.segment_progress.current_since} ~ ${task.segment_progress.current_until}`
                            : ""}
                    </p>
                ) : null}
            </div>
        </div>
    );
}

/**
 * 主组件：爬取过程中实时数据预览
 */
export function LiveCrawlPreview({ task }: LiveCrawlPreviewProps) {
    const isRunning = task.status === "running" || task.status === "pending";
    const isPaused = task.status === "paused";
    const previewTweets: Record<string, unknown>[] = React.useMemo(
        () => task.preview_tweets ?? task.tweets ?? [],
        [task.preview_tweets, task.tweets]
    );
    const hasData = previewTweets.length > 0;

    // 追踪新出现的 tweet ID，触发飞入动画
    const prevIdsRef = React.useRef<Set<string>>(new Set());
    const [newIds, setNewIds] = React.useState<Set<string>>(new Set());

    React.useEffect(() => {
        const currentIds = new Set(
            previewTweets.map((t) => (t.id as string) || "")
        );
        const freshIds = new Set(
            [...currentIds].filter((id) => id && !prevIdsRef.current.has(id))
        );
        if (freshIds.size > 0) {
            setNewIds(freshIds);
            const timer = setTimeout(() => setNewIds(new Set()), 1000);
            prevIdsRef.current = currentIds;
            return () => clearTimeout(timer);
        }
        prevIdsRef.current = currentIds;
    }, [previewTweets]);

    // 运行中无数据：显示精确阶段动画
    if (isRunning && !hasData) {
        return (
            <CrawlingEmptyState
                currentPage={task.current_page}
                crawlPhase={task.crawl_phase}
            />
        );
    }

    // 暂停中无数据：显示暂停 banner
    if (isPaused && !hasData) {
        return <PausedBanner resultCount={task.result_count} />;
    }

    // 有数据：状态 banner + 推文预览卡片
    return (
        <div className="space-y-3">
            {/* 紧凑状态横幅 */}
            <LiveStatusBanner task={task} previewCount={previewTweets.length} />

            {/* 数量提示（仅在预览条数 < 总数时） */}
            {task.result_count > previewTweets.length && (
                <div className="text-center py-2 text-xs text-muted-foreground bg-muted/30 rounded-lg border border-dashed">
                    共抓取{" "}
                    <span className="font-semibold text-foreground">{task.result_count}</span>{" "}
                    条，实时预览最新{" "}
                    <span className="font-semibold text-foreground">{previewTweets.length}</span>{" "}
                    条，任务完成后可查看全部
                </div>
            )}

            {/* 推文卡片列表，新增条目有飞入动效 */}
            <div className="space-y-3">
                {previewTweets.map((tweet, idx) => {
                    const id = (tweet.id as string) || `preview-${idx}`;
                    const isNew = newIds.has(id);
                    return (
                        <div
                            key={id}
                            className={cn(
                                isNew
                                    ? "animate-in fade-in slide-in-from-top-3 duration-500"
                                    : ""
                            )}
                        >
                            <TweetCard tweet={tweet} />
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
