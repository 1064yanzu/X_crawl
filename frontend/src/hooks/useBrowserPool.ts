"use client";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, BrowserPoolStatus } from "@/services/api";

const POLL_INTERVAL_MS = 10_000;
export const BROWSER_POOL_QUERY_KEY = ["browser-pool"] as const;

/**
 * 浏览器池状态查询 hook。
 *
 * 走 React Query：
 * - 同一组件树多处订阅自动合并（queryKey 去重）
 * - `refetchIntervalInBackground:false` → 浏览器最小化或切到其他标签时暂停
 * - 失败/超时由 fetchApi 的 AbortSignal.timeout 兜底
 */
export function useBrowserPool() {
    const queryClient = useQueryClient();
    const [isResizing, setIsResizing] = React.useState(false);

    const query = useQuery({
        queryKey: BROWSER_POOL_QUERY_KEY,
        queryFn: () => api.browserPool.status(),
        refetchInterval: POLL_INTERVAL_MS,
        refetchIntervalInBackground: false,
        placeholderData: (prev) => prev,
    });

    const refetch = React.useCallback(async (): Promise<BrowserPoolStatus | null> => {
        const res = await query.refetch();
        return res.data ?? null;
    }, [query]);

    const resize = React.useCallback(async (newMax: number) => {
        setIsResizing(true);
        try {
            const result = await api.browserPool.resize(newMax);
            // 立即刷新缓存并通知所有订阅者
            await queryClient.invalidateQueries({ queryKey: BROWSER_POOL_QUERY_KEY });
            return result;
        } finally {
            setIsResizing(false);
        }
    }, [queryClient]);

    return {
        data: query.data ?? null,
        isLoading: query.isLoading,
        isResizing,
        error: query.error ? (query.error instanceof Error ? query.error.message : String(query.error)) : null,
        resize,
        refetch,
    };
}
