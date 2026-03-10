"use client";

import * as React from "react";
import {
    buildTweetSearchText,
    getTweetEngagement,
    getTweetLinkCount,
    getTweetMediaCount,
    getTweetMetric,
    getTweetReplyCount,
    getTweetTimestamp,
    matchesResultFilter,
    type ResultDensity,
    type ResultFilter,
    type ResultSort,
    type TweetRecord,
} from "@/lib/task-results";

const PAGE_SIZE_STORAGE_KEY = "task-result-page-size";
const DENSITY_STORAGE_KEY = "task-result-density";

export function useTaskResultState(finishedTweets: TweetRecord[], taskId?: string) {
    const [resultQuery, setResultQuery] = React.useState("");
    const [resultFilter, setResultFilter] = React.useState<ResultFilter>("all");
    const [resultSort, setResultSort] = React.useState<ResultSort>("newest");
    const [resultPage, setResultPage] = React.useState(1);
    const [resultPageSize, setResultPageSize] = React.useState(10);
    const [resultPageInput, setResultPageInput] = React.useState("1");
    const [resultDensity, setResultDensity] = React.useState<ResultDensity>("comfortable");
    const normalizedResultQuery = resultQuery.trim().toLowerCase();

    const filteredFinishedTweets = React.useMemo(() => {
        const matched = finishedTweets.filter((tweet) => {
            if (!matchesResultFilter(tweet, resultFilter)) return false;
            if (!normalizedResultQuery) return true;
            return buildTweetSearchText(tweet).includes(normalizedResultQuery);
        });

        const sorted = [...matched];
        sorted.sort((left, right) => {
            if (resultSort === "oldest") return getTweetTimestamp(left) - getTweetTimestamp(right);
            if (resultSort === "likes") return getTweetMetric(right, "likes") - getTweetMetric(left, "likes");
            if (resultSort === "engagement") return getTweetEngagement(right) - getTweetEngagement(left);
            return getTweetTimestamp(right) - getTweetTimestamp(left);
        });
        return sorted;
    }, [finishedTweets, normalizedResultQuery, resultFilter, resultSort]);

    const resultStats = React.useMemo(
        () =>
            finishedTweets.reduce<{ media: number; replies: number; links: number }>(
                (acc, tweet) => {
                    if (getTweetMediaCount(tweet) > 0) acc.media += 1;
                    if (getTweetReplyCount(tweet) > 0) acc.replies += 1;
                    if (getTweetLinkCount(tweet) > 0) acc.links += 1;
                    return acc;
                },
                { media: 0, replies: 0, links: 0 },
            ),
        [finishedTweets],
    );

    React.useEffect(() => {
        if (typeof window === "undefined") return;
        const savedPageSize = window.localStorage.getItem(PAGE_SIZE_STORAGE_KEY);
        const parsed = savedPageSize ? Number(savedPageSize) : Number.NaN;
        if ([10, 20, 50].includes(parsed)) {
            setResultPageSize(parsed);
        }

        const savedDensity = window.localStorage.getItem(DENSITY_STORAGE_KEY);
        if (savedDensity === "comfortable" || savedDensity === "compact") {
            setResultDensity(savedDensity);
        }
    }, []);

    React.useEffect(() => {
        if (typeof window === "undefined") return;
        window.localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(resultPageSize));
    }, [resultPageSize]);

    React.useEffect(() => {
        if (typeof window === "undefined") return;
        window.localStorage.setItem(DENSITY_STORAGE_KEY, resultDensity);
    }, [resultDensity]);

    React.useEffect(() => {
        setResultPage(1);
    }, [normalizedResultQuery, resultFilter, resultSort, resultPageSize, taskId]);

    const totalResultPages = Math.max(1, Math.ceil(filteredFinishedTweets.length / resultPageSize));
    const visibleResultPage = Math.min(resultPage, totalResultPages);

    React.useEffect(() => {
        if (resultPage > totalResultPages) {
            setResultPage(totalResultPages);
        }
    }, [resultPage, totalResultPages]);

    React.useEffect(() => {
        setResultPageInput(String(visibleResultPage));
    }, [visibleResultPage]);

    const paginatedFinishedTweets = React.useMemo(() => {
        const start = (visibleResultPage - 1) * resultPageSize;
        return filteredFinishedTweets.slice(start, start + resultPageSize);
    }, [filteredFinishedTweets, resultPageSize, visibleResultPage]);

    const goToResultPage = React.useCallback((page: number) => {
        setResultPage(Math.max(1, Math.min(totalResultPages, page)));
    }, [totalResultPages]);

    const resetResultFilters = React.useCallback(() => {
        setResultQuery("");
        setResultFilter("all");
        setResultSort("newest");
    }, []);

    return {
        resultQuery,
        setResultQuery,
        resultFilter,
        setResultFilter,
        resultSort,
        setResultSort,
        resultPageSize,
        setResultPageSize,
        resultPageInput,
        setResultPageInput,
        resultDensity,
        setResultDensity,
        filteredFinishedTweets,
        paginatedFinishedTweets,
        resultStats,
        totalResultPages,
        visibleResultPage,
        goToResultPage,
        resetResultFilters,
    };
}
