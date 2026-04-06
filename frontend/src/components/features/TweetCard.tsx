"use client";
import * as React from "react";
import {
    MessageCircle, Heart, Repeat, Share, ExternalLink,
    Image as ImageIcon, Video, BookmarkIcon, Eye,
    ChevronDown, ChevronUp, Link2, Quote
} from "lucide-react";
import { cn } from "@/lib/utils";
import { VerifiedBadge } from "./VerifiedBadge";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRecord = Record<string, any>;

interface TweetCardProps {
    tweet: AnyRecord;
    isReply?: boolean;    // 作为回复出现时，样式更紧凑
    depth?: number;       // 嵌套深度（0 = 顶层）
    compact?: boolean;
}

function formatCount(n: number | undefined | null): string {
    if (!n || n === 0) return "";
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
}

function formatDate(dateStr: string): string {
    try {
        return new Date(dateStr).toLocaleDateString("zh-CN", {
            month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        });
    } catch {
        return dateStr || "";
    }
}

/**
 * 媒体展示组件（图片/视频，显示实际内容，附带直链）
 */
function MediaGrid({ media, compact = false }: { media: AnyRecord[]; compact?: boolean }) {
    if (!media || media.length === 0) return null;

    return (
        <div className={cn(
            "mt-3 grid gap-1 overflow-hidden rounded-2xl border border-border/30",
            media.length === 1 ? "grid-cols-1" : "grid-cols-2"
        )}>
            {media.map((m: AnyRecord, i: number) => {
                const isVideo = m.type === "video" || m.type === "animated_gif";
                // 图片使用 media_url_https（原始 URL），不使用 expanded_url（那是 x.com 页面链接）
                const imageUrl = m.url || m.media_url_https || "";
                const videoUrl = m.video_url || m.hls_url || "";

                return (
                    <div
                        key={m.id || i}
                        className={cn(
                            "relative bg-muted group/media overflow-hidden",
                            media.length === 3 && i === 0 ? "row-span-2" : ""
                        )}
                    >
                        {isVideo ? (
                            videoUrl ? (
                                <video
                                    src={videoUrl}
                                    controls
                                    playsInline
                                    preload="metadata"
                                    className={cn("w-full h-full object-cover", compact ? "max-h-[240px]" : "max-h-[400px]")}
                                    poster={imageUrl}
                                />
                            ) : (
                                // 没有直接视频 URL（如 HLS 流），显示封面图和跳转链接
                                <a href={m.expanded_url || "#"} target="_blank" rel="noreferrer" className="block">
                                    {/* eslint-disable-next-line @next/next/no-img-element */}
                                    <img
                                        src={imageUrl}
                                        alt={m.alt_text || "视频封面"}
                                        className={cn("w-full h-full object-cover", compact ? "max-h-[240px]" : "max-h-[400px]")}
                                    />
                                    <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                                        <div className="w-14 h-14 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
                                            <Video className="w-7 h-7 text-white" />
                                        </div>
                                    </div>
                                </a>
                            )
                        ) : (
                            <a
                                href={m.expanded_url || imageUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="block"
                                title={m.alt_text || "点击查看原图"}
                            >
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img
                                    src={imageUrl}
                                    alt={m.alt_text || "推文配图"}
                                    className={cn("w-full h-full object-cover hover:opacity-95 transition-opacity", compact ? "max-h-[240px]" : "max-h-[400px]")}
                                />
                            </a>
                        )}
                        {/* 媒体类型角标 */}
                        <div className="absolute top-2 right-2 opacity-0 group-hover/media:opacity-100 transition-opacity">
                            <div className="flex items-center gap-1 bg-black/60 text-white text-xs px-2 py-1 rounded-full">
                                {isVideo ? <Video className="w-3 h-3" /> : <ImageIcon className="w-3 h-3" />}
                                <span>{isVideo ? (m.type === "animated_gif" ? "GIF" : "视频") : "图片"}</span>
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

/**
 * 单条回复卡片（紧凑版）
 */
function ReplyCard({ reply }: { reply: AnyRecord }) {
    const author: AnyRecord = reply.author || {};
    const metrics: AnyRecord = reply.metrics || {};
    const media: AnyRecord[] = reply.media || [];

    return (
        <div className="flex gap-2.5 py-3 border-b border-border/30 last:border-0">
            {/* 竖线连接 */}
            <div className="flex flex-col items-center shrink-0">
                {author.avatar_url ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                        src={author.avatar_url}
                        alt={author.name || "头像"}
                        className={cn(
                            "w-8 h-8 object-cover shrink-0",
                            author.profile_image_shape === "Square" ? "rounded-lg" : "rounded-full"
                        )}
                    />
                ) : (
                    <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs font-bold text-muted-foreground">
                        {(author.name as string)?.charAt(0) || "?"}
                    </div>
                )}
            </div>

            <div className="flex-1 min-w-0">
                {/* Header */}
                <div className="flex items-center gap-1.5 flex-wrap mb-1">
                    <span className="text-sm font-semibold truncate">{author.name || "未知用户"}</span>
                    <VerifiedBadge author={author} />
                    <span className="text-xs text-muted-foreground">@{author.screen_name || "unknown"}</span>
                    <span className="text-xs text-muted-foreground">·</span>
                    <span className="text-xs text-muted-foreground">{formatDate(reply.created_at)}</span>
                </div>

                {/* Text */}
                <div className="text-sm leading-relaxed whitespace-pre-wrap break-words text-foreground/90">
                    {reply.text}
                </div>

                {/* Media */}
                {media.length > 0 && <MediaGrid media={media} />}

                {/* Metrics */}
                <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                        <Heart className="w-3.5 h-3.5" />
                        {formatCount(metrics.likes)}
                    </span>
                    <span className="flex items-center gap-1">
                        <Repeat className="w-3.5 h-3.5" />
                        {formatCount(metrics.retweets)}
                    </span>
                    {reply.url && (
                        <a href={reply.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-primary transition-colors ml-auto">
                            <ExternalLink className="w-3 h-3" />
                        </a>
                    )}
                </div>
            </div>
        </div>
    );
}

/**
 * 主推文卡片
 */
export function TweetCard({ tweet, isReply = false, depth = 0, compact = false }: TweetCardProps) {
    const author: AnyRecord = tweet.author || {};
    const metrics: AnyRecord = tweet.metrics || {};
    const media: AnyRecord[] = tweet.media || [];
    const replies: AnyRecord[] = tweet.replies || [];
    const urls: AnyRecord[] = tweet.urls || [];
    const hashtags: string[] = tweet.hashtags || [];

    const [showReplies, setShowReplies] = React.useState(false);
    const [showFullText, setShowFullText] = React.useState(!compact);
    const tweetText = typeof tweet.text === "string" ? tweet.text : "";
    const canCollapseText = compact && tweetText.length > 180;

    React.useEffect(() => {
        setShowFullText(!compact);
    }, [compact, tweet.id]);

    return (
        <div className={cn(
            "bg-card border rounded-2xl shadow-sm hover:shadow-md transition-shadow relative group",
            isReply ? "p-3 border-border/40" : compact ? "p-4" : "p-5",
            depth > 0 && "ml-4 border-l-2 border-primary/20"
        )}>
            <div className={cn("flex gap-3", compact && !isReply && "gap-2.5")}>
                {/* Avatar */}
                <div className="shrink-0">
                    {author.avatar_url ? (
                        /* eslint-disable-next-line @next/next/no-img-element */
                        <img
                            src={author.avatar_url}
                            alt={(author.name as string) || "头像"}
                            className={cn(
                                "object-cover",
                                isReply ? "w-9 h-9" : compact ? "w-10 h-10" : "w-12 h-12",
                                author.profile_image_shape === "Square" ? "rounded-lg" : "rounded-full"
                            )}
                        />
                    ) : (
                        <div className={cn(
                            "bg-muted rounded-full flex items-center justify-center font-bold text-muted-foreground",
                            isReply ? "w-9 h-9 text-base" : compact ? "w-10 h-10 text-base" : "w-12 h-12 text-lg"
                        )}>
                            {(author.name as string)?.charAt(0) || "?"}
                        </div>
                    )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                    {/* Header */}
                    <div className={cn("flex items-center gap-1.5 flex-wrap", compact ? "mb-0.5" : "mb-1")}>
                        <span className={cn("font-bold truncate hover:underline cursor-pointer", compact ? "text-[14px]" : "text-[15px]")}>
                            {author.name || "未知用户"}
                        </span>
                        <VerifiedBadge author={author} />
                        <span className={cn("text-muted-foreground truncate", compact ? "text-[13px]" : "text-[14px]")}>
                            @{author.screen_name || "未知"}
                        </span>
                        <span className={cn("text-muted-foreground", compact ? "text-[13px]" : "text-[14px]")}>·</span>
                        <span className={cn("text-muted-foreground hover:underline cursor-pointer whitespace-nowrap", compact ? "text-[13px]" : "text-[14px]")}>
                            {formatDate(tweet.created_at as string)}
                        </span>
                    </div>

                    {/* Reply context */}
                    {tweet.reply_to?.screen_name && (
                        <div className={cn("text-xs text-muted-foreground", compact ? "mb-0.5" : "mb-1")}>
                            回复 <span className="text-primary">@{tweet.reply_to.screen_name}</span>
                        </div>
                    )}

                    {/* Text body */}
                    <div className={cn(
                        "leading-normal whitespace-pre-wrap break-words",
                        isReply ? "text-sm" : compact ? "text-[14px]" : "text-[15px]",
                        canCollapseText && !showFullText && "line-clamp-4",
                    )}>
                        {tweetText}
                    </div>
                    {canCollapseText ? (
                        <button
                            type="button"
                            onClick={() => setShowFullText((prev) => !prev)}
                            className="mt-2 text-xs font-medium text-primary hover:text-primary/80"
                        >
                            {showFullText ? "收起正文" : "展开正文"}
                        </button>
                    ) : null}

                    {/* Hashtags */}
                    {hashtags.length > 0 && (
                        <div className={cn("flex flex-wrap gap-1.5", compact ? "mt-1.5" : "mt-2")}>
                            {hashtags.map((tag: string) => (
                                <span key={tag} className="text-xs text-primary hover:underline cursor-pointer">
                                    #{tag}
                                </span>
                            ))}
                        </div>
                    )}

                    {/* External URLs */}
                    {urls.length > 0 && (
                        <div className={cn("flex flex-col gap-1", compact ? "mt-1.5" : "mt-2")}>
                            {urls.map((u: AnyRecord, i: number) => u.expanded_url && (
                                <a
                                    key={i}
                                    href={u.expanded_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="flex items-center gap-1.5 text-xs text-primary hover:underline truncate"
                                >
                                    <Link2 className="w-3 h-3 shrink-0" />
                                    {u.display_url || u.expanded_url}
                                </a>
                            ))}
                        </div>
                    )}

                    {/* Media Grid */}
                    <MediaGrid media={media} compact={compact} />

                    {/* Quoted tweet */}
                    {tweet.quoted_tweet && (
                        <div className={cn("rounded-xl border border-border/50 bg-muted/20", compact ? "mt-2.5 p-2.5" : "mt-3 p-3")}>
                            <div className="flex items-center gap-1.5 mb-1">
                                <Quote className="w-3.5 h-3.5 text-muted-foreground" />
                                <span className="text-xs text-muted-foreground font-medium">引用推文</span>
                            </div>
                            <TweetCard tweet={tweet.quoted_tweet as AnyRecord} isReply depth={depth + 1} compact={compact} />
                        </div>
                    )}

                    {/* Metrics Footer */}
                    <div className={cn("flex items-center justify-between text-muted-foreground max-w-md", compact ? "mt-2.5" : "mt-3")}>
                        <div className="flex items-center gap-1.5 hover:text-blue-500 transition-colors cursor-pointer group/action">
                            <div className="p-1.5 rounded-full group-hover/action:bg-blue-500/10">
                                <MessageCircle className="w-4 h-4" />
                            </div>
                            <span className="text-[13px]">{formatCount(metrics.replies)}</span>
                        </div>
                        <div className="flex items-center gap-1.5 hover:text-green-500 transition-colors cursor-pointer group/action">
                            <div className="p-1.5 rounded-full group-hover/action:bg-green-500/10">
                                <Repeat className="w-4 h-4" />
                            </div>
                            <span className="text-[13px]">{formatCount(metrics.retweets)}</span>
                        </div>
                        <div className="flex items-center gap-1.5 hover:text-red-500 transition-colors cursor-pointer group/action">
                            <div className="p-1.5 rounded-full group-hover/action:bg-red-500/10">
                                <Heart className="w-4 h-4" />
                            </div>
                            <span className="text-[13px]">{formatCount(metrics.likes)}</span>
                        </div>
                        <div className="flex items-center gap-1.5 hover:text-amber-500 transition-colors cursor-pointer group/action">
                            <div className="p-1.5 rounded-full group-hover/action:bg-amber-500/10">
                                <BookmarkIcon className="w-4 h-4" />
                            </div>
                            <span className="text-[13px]">{formatCount(metrics.bookmarks)}</span>
                        </div>
                        {metrics.views != null && metrics.views > 0 && (
                            <div className="flex items-center gap-1 text-muted-foreground/70">
                                <Eye className="w-3.5 h-3.5" />
                                <span className="text-[12px]">{formatCount(metrics.views)}</span>
                            </div>
                        )}
                        <div className="flex items-center gap-1.5 hover:text-blue-500 transition-colors cursor-pointer group/action">
                            <div className="p-1.5 rounded-full group-hover/action:bg-blue-500/10">
                                <Share className="w-4 h-4" />
                            </div>
                        </div>
                    </div>

                    {/* Replies section */}
                    {replies.length > 0 && (
                        <div className={cn(compact ? "mt-2.5" : "mt-3")}>
                            <button
                                type="button"
                                onClick={() => setShowReplies(!showReplies)}
                                className="flex items-center gap-2 text-xs font-medium text-primary hover:text-primary/80 transition-colors py-1.5 px-3 rounded-lg hover:bg-primary/5"
                            >
                                <MessageCircle className="w-3.5 h-3.5" />
                                {showReplies ? "收起" : "展开"} {replies.length} 条回复
                                {showReplies ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                            </button>

                            {showReplies && (
                                <div className="mt-2 border border-border/30 rounded-xl overflow-hidden bg-muted/10 px-3">
                                    {replies.map((reply: AnyRecord, idx: number) => (
                                        <ReplyCard key={reply.id ? `${reply.id}-${idx}` : `reply-${idx}`} reply={reply} />
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* External Link Overlay */}
            {tweet.url && (
                <a
                    href={tweet.url as string}
                    target="_blank"
                    rel="noreferrer"
                    className={cn("absolute text-muted-foreground/30 hover:text-primary transition-colors", compact ? "top-3 right-3" : "top-4 right-4")}
                >
                    <ExternalLink className="w-4 h-4" />
                </a>
            )}
        </div>
    );
}
