"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
    api,
    type SearchRequest,
    type YouTubeOrder,
    type YouTubeSearchParams,
    type YouTubeSource,
    type YouTubeType,
    type YouTubeVideoDefinition,
    type YouTubeVideoDuration,
} from "@/services/api";
import { useToast } from "@/components/ui/toast";
import { parseYouTubeVideoIds, readFileAsText } from "@/lib/youtube-url";

const STRATEGY = "dfs" as const;

export function useYouTubeTaskBuilder() {
    const router = useRouter();
    const { push } = useToast();

    const [loading, setLoading] = React.useState(false);
    const [source, setSource] = React.useState<YouTubeSource>("keyword");

    // keyword 分支
    const [keyword, setKeyword] = React.useState("");
    const [type, setType] = React.useState<YouTubeType>("video");
    const [order, setOrder] = React.useState<YouTubeOrder>("relevance");
    const [regionCode, setRegionCode] = React.useState("");
    const [relevanceLanguage, setRelevanceLanguage] = React.useState("");
    const [videoDuration, setVideoDuration] = React.useState<YouTubeVideoDuration>("any");
    const [videoDefinition, setVideoDefinition] = React.useState<YouTubeVideoDefinition>("any");
    const [startDate, setStartDate] = React.useState("");
    const [endDate, setEndDate] = React.useState("");

    // channel 分支
    const [channelInput, setChannelInput] = React.useState("");

    // video_urls 分支
    const [videoUrlsText, setVideoUrlsText] = React.useState("");
    const [videoUrlsFileName, setVideoUrlsFileName] = React.useState("");

    // 共享
    const [maxVideos, setMaxVideos] = React.useState(50);
    const [fetchReplies, setFetchReplies] = React.useState(false);
    const [replyDepth, setReplyDepth] = React.useState(2);

    const parsedVideoIds = React.useMemo(
        () => parseYouTubeVideoIds(videoUrlsText),
        [videoUrlsText],
    );

    const onVideoUrlsFileSelected = React.useCallback(
        async (file: File | null) => {
            if (!file) return;
            try {
                const text = await readFileAsText(file);
                setVideoUrlsText((prev) => (prev.trim() ? `${prev.trim()}\n${text}` : text));
                setVideoUrlsFileName(file.name);
            } catch (error) {
                push({
                    type: "error",
                    title: "读取文件失败",
                    description: error instanceof Error ? error.message : String(error),
                });
            }
        },
        [push],
    );

    const clearVideoUrls = React.useCallback(() => {
        setVideoUrlsText("");
        setVideoUrlsFileName("");
    }, []);

    const buildPayload = React.useCallback((): SearchRequest => {
        if (source === "keyword" && !keyword.trim()) {
            throw new Error("YouTube 关键词采集需要填写关键词。");
        }
        if (source === "channel" && !channelInput.trim()) {
            throw new Error("YouTube 频道采集需要填写频道 ID / @handle / URL。");
        }
        if (source === "video_urls" && parsedVideoIds.ids.length === 0) {
            throw new Error("YouTube 视频链接批量采集至少需要 1 个有效链接或视频 ID。");
        }
        if (source === "keyword" && startDate && endDate && startDate > endDate) {
            throw new Error("YouTube 时间范围无效，结束日期需要晚于开始日期。");
        }

        const keywordForTask =
            source === "keyword"
                ? keyword.trim()
                : source === "channel"
                  ? channelInput.trim()
                  : `youtube-urls · ${parsedVideoIds.ids.length} 视频`;

        const youtube: YouTubeSearchParams = {
            source,
            channel_input: source === "channel" ? channelInput.trim() : null,
            video_urls: source === "video_urls" ? parsedVideoIds.ids : null,
            type: source === "keyword" ? type : "video",
            order: source === "keyword" ? order : "relevance",
            region_code: source === "keyword" ? regionCode.trim() || null : null,
            relevance_language: source === "keyword" ? relevanceLanguage.trim() || null : null,
            video_duration: source === "keyword" ? videoDuration : "any",
            video_definition: source === "keyword" ? videoDefinition : "any",
            max_videos:
                source === "video_urls"
                    ? 0
                    : Math.max(1, Math.min(500, maxVideos || 50)),
        };

        return {
            keyword: keywordForTask,
            product: "Latest",
            resume: true,
            fetch_replies: fetchReplies,
            max_replies_per_tweet: 0,
            reply_depth: replyDepth,
            crawl_strategy: STRATEGY,
            platform: "youtube",
            start_date: source === "keyword" && startDate ? startDate : undefined,
            end_date: source === "keyword" && endDate ? endDate : undefined,
            youtube,
        };
    }, [
        channelInput,
        endDate,
        fetchReplies,
        keyword,
        maxVideos,
        order,
        parsedVideoIds.ids,
        regionCode,
        relevanceLanguage,
        replyDepth,
        source,
        startDate,
        type,
        videoDefinition,
        videoDuration,
    ]);

    const resetDraft = React.useCallback(() => {
        if (source === "keyword") {
            setKeyword("");
        } else if (source === "channel") {
            setChannelInput("");
        } else {
            clearVideoUrls();
        }
    }, [clearVideoUrls, source]);

    const submit = React.useCallback(async () => {
        setLoading(true);
        try {
            const payload = buildPayload();
            const task = await api.search.create(payload);
            push({ type: "success", title: "YouTube 任务已提交", description: "正在跳转任务详情。" });
            router.push(`/tasks/${task.task_id}`);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            if (message.includes("409")) {
                push({ type: "error", title: "当前并发任务已达上限", description: "请等待正在运行任务结束后再创建新任务。" });
            } else {
                push({ type: "error", title: "启动 YouTube 任务失败", description: message });
            }
        } finally {
            setLoading(false);
        }
    }, [buildPayload, push, router]);

    const canSubmit = React.useMemo(() => {
        if (source === "keyword") return keyword.trim().length > 0;
        if (source === "channel") return channelInput.trim().length > 0;
        return parsedVideoIds.ids.length > 0;
    }, [channelInput, keyword, parsedVideoIds.ids.length, source]);

    return {
        loading,
        source,
        setSource,
        keyword,
        setKeyword,
        type,
        setType,
        order,
        setOrder,
        regionCode,
        setRegionCode,
        relevanceLanguage,
        setRelevanceLanguage,
        videoDuration,
        setVideoDuration,
        videoDefinition,
        setVideoDefinition,
        startDate,
        setStartDate,
        endDate,
        setEndDate,
        channelInput,
        setChannelInput,
        videoUrlsText,
        setVideoUrlsText,
        videoUrlsFileName,
        onVideoUrlsFileSelected,
        clearVideoUrls,
        parsedVideoIds,
        maxVideos,
        setMaxVideos,
        fetchReplies,
        setFetchReplies,
        replyDepth,
        setReplyDepth,
        canSubmit,
        buildPayload,
        resetDraft,
        submit,
    };
}

export type UseYouTubeTaskBuilderReturn = ReturnType<typeof useYouTubeTaskBuilder>;
