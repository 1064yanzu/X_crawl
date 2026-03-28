"use client";
import * as React from "react";
import { api, BrowserPoolStatus } from "@/services/api";

const POLL_INTERVAL_MS = 5000;

export function useBrowserPool() {
    const [data, setData] = React.useState<BrowserPoolStatus | null>(null);
    const [isLoading, setIsLoading] = React.useState(true);
    const [isResizing, setIsResizing] = React.useState(false);
    const [error, setError] = React.useState<string | null>(null);

    const fetchStatus = React.useCallback(async () => {
        try {
            const status = await api.browserPool.status();
            setData(status);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setIsLoading(false);
        }
    }, []);

    // 初始拉取 + 轮询
    React.useEffect(() => {
        void fetchStatus();
        const timer = setInterval(() => void fetchStatus(), POLL_INTERVAL_MS);
        return () => clearInterval(timer);
    }, [fetchStatus]);

    const resize = React.useCallback(async (newMax: number) => {
        setIsResizing(true);
        try {
            const result = await api.browserPool.resize(newMax);
            // 立即刷新状态
            await fetchStatus();
            return result;
        } finally {
            setIsResizing(false);
        }
    }, [fetchStatus]);

    return { data, isLoading, isResizing, error, resize, refetch: fetchStatus };
}
