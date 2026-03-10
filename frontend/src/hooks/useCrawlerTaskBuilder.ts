"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { api, type CrawlStrategy, type Platform, type SearchRequest } from "@/services/api";
import { useToast } from "@/components/ui/toast";
import { buildAdvancedQuery, DEFAULT_ADVANCED_PARAMS, type AdvancedSearchParams } from "@/lib/advanced-search";

const STRATEGY: CrawlStrategy = "dfs";

export function useCrawlerTaskBuilder(productDefault: "Top" | "Latest" | "Photos" | "Videos" = "Top") {
    const router = useRouter();
    const { push } = useToast();
    const [loading, setLoading] = React.useState(false);
    const [keyword, setKeyword] = React.useState("");
    const [maxCount, setMaxCount] = React.useState(0);
    const [product, setProduct] = React.useState<typeof productDefault>(productDefault);
    const [advancedParams, setAdvancedParams] = React.useState<AdvancedSearchParams>(DEFAULT_ADVANCED_PARAMS);
    const [advancedOpen, setAdvancedOpen] = React.useState(false);
    const [fetchReplies, setFetchReplies] = React.useState(false);
    const [replyDepth, setReplyDepth] = React.useState(2);
    const [platform, setPlatform] = React.useState<Platform>("x");
    const [startDate, setStartDate] = React.useState("");
    const [endDate, setEndDate] = React.useState("");
    const [splitTriggerDays, setSplitTriggerDays] = React.useState(30);

    React.useEffect(() => {
        api.crawlerConfig.get()
            .then((cfg) => setSplitTriggerDays(cfg.x_time_split_trigger_days ?? 30))
            .catch(() => undefined);
    }, []);

    const finalKeyword = React.useMemo(() => {
        let query = keyword.trim();
        const advancedQuery = buildAdvancedQuery(advancedParams);
        if (advancedQuery) {
            query = query ? `${query} ${advancedQuery}` : advancedQuery;
        }
        return query;
    }, [advancedParams, keyword]);

    const xSplitNotice = React.useMemo(() => {
        if (platform !== "x" || !advancedParams.since || !advancedParams.until) return null;
        const start = new Date(`${advancedParams.since}T00:00:00`);
        const end = new Date(`${advancedParams.until}T00:00:00`);
        if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
        const days = Math.floor((end.getTime() - start.getTime()) / 86400000);
        if (days < splitTriggerDays) return null;
        if (days >= 90) {
            return `检测到 ${days} 天跨度，将自动按月拆分任务以提升稳定性。`;
        }
        return `检测到 ${days} 天跨度，将按时间窗口自动切片，提升覆盖率与稳定性。`;
    }, [advancedParams.since, advancedParams.until, platform, splitTriggerDays]);

    const submit = React.useCallback(async () => {
        if (!finalKeyword) {
            push({ type: "error", title: "请输入检索关键词或高级筛选条件" });
            return;
        }
        if (platform === "weibo" && startDate && endDate && startDate > endDate) {
            push({ type: "error", title: "微博时间范围无效", description: "结束日期需要晚于开始日期。" });
            return;
        }

        setLoading(true);
        try {
            const payload: SearchRequest = {
                keyword: finalKeyword,
                max_count: maxCount,
                product,
                resume: true,
                fetch_replies: fetchReplies,
                max_replies_per_tweet: 0,
                reply_depth: replyDepth,
                crawl_strategy: STRATEGY,
                platform,
                start_date: platform === "weibo" && startDate ? startDate : undefined,
                end_date: platform === "weibo" && endDate ? endDate : undefined,
            };
            const task = await api.search.create(payload);
            push({ type: "success", title: "采集任务已提交", description: "正在跳转到任务详情。" });
            router.push(`/tasks/${task.task_id}`);
        } catch (error) {
            console.error(error);
            const message = error instanceof Error ? error.message : String(error);
            if (message.includes("409")) {
                push({ type: "error", title: "当前并发任务已达上限", description: "请等待正在运行任务结束后再创建新任务。" });
            } else {
                push({ type: "error", title: "启动采集任务失败", description: message });
            }
        } finally {
            setLoading(false);
        }
    }, [endDate, fetchReplies, finalKeyword, maxCount, platform, product, push, replyDepth, router, startDate]);

    return {
        loading,
        keyword,
        setKeyword,
        maxCount,
        setMaxCount,
        product,
        setProduct,
        advancedParams,
        setAdvancedParams,
        advancedOpen,
        setAdvancedOpen,
        fetchReplies,
        setFetchReplies,
        replyDepth,
        setReplyDepth,
        platform,
        setPlatform,
        startDate,
        setStartDate,
        endDate,
        setEndDate,
        finalKeyword,
        xSplitNotice,
        canSubmit: Boolean(finalKeyword),
        submit,
    };
}
