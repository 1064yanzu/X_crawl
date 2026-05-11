"use client";

import * as React from "react";
import {
    ChevronDown,
    ChevronUp,
    Eye,
    ExternalLink,
    Heart,
    Loader2,
    MessageCircle,
    PlayCircle,
    Radio,
    Youtube as YoutubeIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRecord = Record<string, any>;

interface Props {
    tweet: AnyRecord;
    compact?: boolean;
}

interface ReplyProps {
    reply: AnyRecord;
}

function formatCount(n: number | undefined | null): string {
    if (!n || n === 0) return "0";
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
}

function formatDate(dateStr: string): string {
    if (!dateStr) return "";
    try {
        return new Date(dateStr).toLocaleString("zh-CN", {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        });
    } catch {
        return dateStr;
    }
}

function formatDuration(sec: number | null | undefined): string {
    if (!sec || sec <= 0) return "";
    const hours = Math.floor(sec / 3600);
    const minutes = Math.floor((sec % 3600) / 60);
    const seconds = sec % 60;
    const pad = (n: number) => n.toString().padStart(2, "0");
    if (hours > 0) return `${hours}:${pad(minutes)}:${pad(seconds)}`;
    return `${minutes}:${pad(seconds)}`;
}

function YouTubeCommentCard({ reply }: ReplyProps) {
    const author: AnyRecord = reply.author || {};
    const metrics: AnyRecord = reply.metrics || {};
    const childReplies: AnyRecord[] = reply.replies || [];
    const [expanded, setExpanded] = React.useState(false);

    return (
        <div className="border-b border-border py-3 last:border-0">
            <div className="flex gap-2.5">
                {author.avatar_url ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                        src={author.avatar_url}
                        alt={author.name || "头像"}
                        className="h-8 w-8 shrink-0 rounded-full object-cover"
                    />
                ) : (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold text-muted-foreground">
                        {(author.name as string)?.charAt(0) || "?"}
                    </div>
                )}
                <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-center gap-2">
                        <span className="truncate text-sm font-semibold">{author.name || "匿名用户"}</span>
                        <span className="text-xs text-muted-foreground">{formatDate(reply.created_at)}</span>
                    </div>
                    <div
                        className="whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground/90"
                        dangerouslySetInnerHTML={{ __html: reply.text || "" }}
                    />
                    <div className="mt-2 flex items-center gap-4 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                            <Heart className="h-3.5 w-3.5" />
                            {formatCount(metrics.likes)}
                        </span>
                        {metrics.replies > 0 && (
                            <button
                                type="button"
                                onClick={() => setExpanded((v) => !v)}
                                className="inline-flex items-center gap-1 transition-colors hover:text-primary"
                            >
                                <MessageCircle className="h-3.5 w-3.5" />
                                {metrics.replies} 条回复
                                {childReplies.length > 0 ? (
                                    expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />
                                ) : null}
                            </button>
                        )}
                    </div>

                    {expanded && childReplies.length > 0 && (
                        <div className="mt-3 space-y-2 border-l-2 border-border pl-3">
                            {childReplies.map((child: AnyRecord, idx: number) => (
                                <YouTubeCommentCard key={child.id ? `${child.id}-${idx}` : `child-${idx}`} reply={child} />
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export function YouTubeVideoCard({ tweet, compact = false }: Props) {
    const author: AnyRecord = tweet.author || {};
    const metrics: AnyRecord = tweet.metrics || {};
    const media: AnyRecord[] = Array.isArray(tweet.media) ? tweet.media : [];
    const replies: AnyRecord[] = Array.isArray(tweet.replies) ? tweet.replies : [];
    const extra: AnyRecord = tweet.platform_extra || {};
    const title: string = extra.title || (typeof tweet.text === "string" ? tweet.text.split("\n")[0] : "") || "无标题视频";
    const description: string = extra.description || (typeof tweet.text === "string" ? tweet.text.split("\n\n").slice(1).join("\n\n") : "");
    const thumb = media[0]?.url || extra.thumbnail?.url || "";
    const durationSec: number | null = typeof extra.duration_sec === "number" ? extra.duration_sec : null;
    const liveBroadcast: string = extra.live_broadcast_content || "";
    const videoUrl: string = tweet.url || `https://www.youtube.com/watch?v=${tweet.id}`;
    const channelUrl = extra.channel_id ? `https://www.youtube.com/channel/${extra.channel_id}` : "";
    const commentStats: AnyRecord = (extra.comment_stats && typeof extra.comment_stats === "object")
        ? (extra.comment_stats as AnyRecord)
        : {};
    const commentPhase: string = typeof commentStats.phase === "string" ? commentStats.phase : "";
    const commentsDisabled: boolean = Boolean(commentStats.comments_disabled);
    const commentPages: number = typeof commentStats.pages_fetched === "number" ? commentStats.pages_fetched : 0;
    const fetchedTopLevel: number = typeof commentStats.fetched_top_level_count === "number" ? commentStats.fetched_top_level_count : 0;
    const fetchedTotal: number = typeof commentStats.fetched_total_count === "number" ? commentStats.fetched_total_count : 0;
    const commentError: string = typeof extra.comment_error === "string" ? (extra.comment_error as string) : "";
    const totalExpectedComments: number = typeof metrics.replies === "number" ? (metrics.replies as number) : 0;
    const progressRatio = totalExpectedComments > 0
        ? Math.min(1, fetchedTotal / totalExpectedComments)
        : 0;

    const [showDescription, setShowDescription] = React.useState(false);
    const [showReplies, setShowReplies] = React.useState(false);

    return (
        <div
            className={cn(
 "group relative overflow-hidden rounded-md border border-border bg-card shadow-sm transition-shadow hover:shadow-md",
                compact ? "p-3" : "p-4",
            )}
        >
            <div className={cn("grid gap-4", compact ? "md:grid-cols-[200px_1fr]" : "md:grid-cols-[320px_1fr]")}>
                <a
                    href={videoUrl}
                    target="_blank"
                    rel="noreferrer"
                    className={cn(
 "group/thumb relative block aspect-video overflow-hidden rounded-md bg-muted",
                    )}
                    title={title}
                >
                    {thumb ? (
                        /* eslint-disable-next-line @next/next/no-img-element */
                        <img
                            src={thumb}
                            alt={title}
                            className="h-full w-full object-cover transition-transform group-hover/thumb:scale-105"
                        />
                    ) : (
                        <div className="flex h-full w-full items-center justify-center text-muted-foreground">
                            <YoutubeIcon className="h-10 w-10 text-red-500" />
                        </div>
                    )}
                    <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-t from-black/50 to-transparent opacity-0 transition-opacity group-hover/thumb:opacity-100">
                        <PlayCircle className="h-14 w-14 text-white drop-shadow-lg" strokeWidth={1.5} />
                    </div>
                    {durationSec !== null && durationSec > 0 && (
                        <span className="absolute bottom-2 right-2 rounded-md bg-black/80 px-2 py-0.5 text-xs font-medium text-white shadow-sm">
                            {formatDuration(durationSec)}
                        </span>
                    )}
                    {liveBroadcast === "live" && (
                        <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-md bg-red-600 px-2 py-0.5 text-xs font-bold text-white">
                            <Radio className="h-3 w-3 animate-pulse" /> 直播中
                        </span>
                    )}
                    {liveBroadcast === "upcoming" && (
                        <span className="absolute left-2 top-2 rounded-md bg-amber-500 px-2 py-0.5 text-xs font-bold text-white">
                            即将开始
                        </span>
                    )}
                </a>

                <div className="flex min-w-0 flex-col">
                    <div className="flex items-start justify-between gap-2">
                        <a
                            href={videoUrl}
                            target="_blank"
                            rel="noreferrer"
                            className={cn(
 "font-semibold leading-snug text-foreground transition-colors hover:text-red-600 line-clamp-2 dark:hover:text-red-400",
                                compact ? "text-[15px]" : "text-lg",
                            )}
                            title={title}
                        >
                            {title}
                        </a>
                        <a
                            href={videoUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="shrink-0 text-muted-foreground/60 transition-colors hover:text-red-500"
                            title="在 YouTube 打开"
                        >
                            <ExternalLink className="h-4 w-4" />
                        </a>
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                        {channelUrl ? (
                            <a
                                href={channelUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 font-medium text-foreground/80 hover:text-red-600 dark:hover:text-red-400"
                            >
                                <YoutubeIcon className="h-3.5 w-3.5 text-red-500" />
                                {author.name || extra.channel_title || "未知频道"}
                            </a>
                        ) : (
                            <span className="inline-flex items-center gap-1 font-medium text-foreground/80">
                                <YoutubeIcon className="h-3.5 w-3.5 text-red-500" />
                                {author.name || extra.channel_title || "未知频道"}
                            </span>
                        )}
                        <span>·</span>
                        <span>{formatDate(tweet.created_at)}</span>
                        {extra.category_id && (
                            <>
                                <span>·</span>
                                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                                    分类 {extra.category_id}
                                </span>
                            </>
                        )}
                    </div>

                    <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                        <span className="inline-flex items-center gap-1.5">
                            <Eye className="h-4 w-4" />
                            <span className="font-medium text-foreground">{formatCount(metrics.views)}</span>
                            <span>观看</span>
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                            <Heart className="h-4 w-4" />
                            <span className="font-medium text-foreground">{formatCount(metrics.likes)}</span>
                            <span>点赞</span>
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                            <MessageCircle className="h-4 w-4" />
                            <span className="font-medium text-foreground">{formatCount(metrics.replies)}</span>
                            <span>评论</span>
                        </span>
                    </div>

                    {description && (
                        <div className="mt-3">
                            <p
                                className={cn(
 "whitespace-pre-wrap text-sm leading-relaxed text-foreground/80",
                                    !showDescription && "line-clamp-3",
                                )}
                            >
                                {description}
                            </p>
                            {description.length > 120 && (
                                <button
                                    type="button"
                                    onClick={() => setShowDescription((v) => !v)}
                                    className="mt-1 text-xs font-medium text-red-600 transition-colors hover:text-red-500 dark:text-red-400"
                                >
                                    {showDescription ? "收起简介" : "展开简介"}
                                </button>
                            )}
                        </div>
                    )}

                    {Array.isArray(tweet.hashtags) && tweet.hashtags.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                            {tweet.hashtags.slice(0, 8).map((tag: string) => (
                                <span
                                    key={tag}
                                    className="rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs text-red-600 dark:text-red-300"
                                >
                                    #{tag}
                                </span>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {(commentPhase || replies.length > 0 || commentsDisabled || commentError) && (
                <div className="mt-4 border-t border-border pt-3">
                    {/* 实时评论抓取进度 */}
                    {(commentPhase === "running" || commentPhase === "quota_exhausted") && !commentsDisabled && (
                        <div className="mb-3 rounded-md border border-red-500/20 bg-red-500/5 px-3 py-2.5">
                            <div className="flex items-center gap-2 text-xs font-medium">
                                {commentPhase === "running" ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin text-red-500" />
                                ) : (
                                    <MessageCircle className="h-3.5 w-3.5 text-amber-500" />
                                )}
                                <span className="text-foreground/90">
                                    {commentPhase === "running" ? "评论抓取中" : "评论抓取暂停（配额耗尽）"}
                                </span>
                                <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                                    第 {commentPages} 页
                                </span>
                            </div>
                            <div className="mt-1.5 flex items-center gap-3 text-[11px] text-muted-foreground">
                                <span>顶级 <span className="font-semibold text-foreground">{fetchedTopLevel}</span></span>
                                <span>·</span>
                                <span>总计 <span className="font-semibold text-foreground">{fetchedTotal}</span></span>
                                {totalExpectedComments > 0 && (
                                    <>
                                        <span>·</span>
                                        <span>目标 <span className="font-semibold text-foreground">{totalExpectedComments}</span></span>
                                    </>
                                )}
                            </div>
                            {totalExpectedComments > 0 && (
                                <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-muted">
                                    <div
                                        className="h-full rounded-full bg-red-500 transition-all duration-500"
                                        style={{ width: `${Math.round(progressRatio * 100)}%` }}
                                    />
                                </div>
                            )}
                        </div>
                    )}
                    {commentPhase === "done" && (commentPages > 0 || fetchedTotal > 0) && (
                        <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 font-medium text-emerald-700 dark:text-emerald-400">
                                评论已抓完
                            </span>
                            <span>{commentPages} 页</span>
                            <span>·</span>
                            <span>顶级 {fetchedTopLevel}</span>
                            <span>·</span>
                            <span>总计 {fetchedTotal}</span>
                        </div>
                    )}
                    {commentsDisabled && (
                        <div className="mb-3 rounded-md border border-muted bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">
                            该视频已关闭评论
                        </div>
                    )}
                    {commentError && (
                        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/5 px-3 py-2 text-[11px] text-red-600 dark:text-red-400">
                            评论抓取失败：{commentError}
                        </div>
                    )}

                    {replies.length > 0 && (
                        <>
                            <button
                                type="button"
                                onClick={() => setShowReplies((v) => !v)}
                                className="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-500/10 dark:text-red-400"
                            >
                                <MessageCircle className="h-3.5 w-3.5" />
                                {showReplies ? "收起" : "展开"} {replies.length} 条评论
                                {showReplies ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                            </button>
                            {showReplies && (
                                <div className="mt-2 rounded-md border border-border bg-muted/10 px-3">
                                    {replies.map((reply: AnyRecord, idx: number) => (
                                        <YouTubeCommentCard key={reply.id ? `${reply.id}-${idx}` : `reply-${idx}`} reply={reply} />
                                    ))}
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
