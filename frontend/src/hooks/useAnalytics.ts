"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";

export const ANALYTICS_QUERY_KEY = ["analytics", "overview"] as const;
export const LIVE_RATES_QUERY_KEY = ["analytics", "live-rates"] as const;

export function useAnalyticsOverview(refetchMs = 30000) {
    return useQuery({
        queryKey: ANALYTICS_QUERY_KEY,
        queryFn: () => api.analytics.overview(),
        refetchInterval: refetchMs,
        refetchIntervalInBackground: false,
        placeholderData: (previousData) => previousData,
    });
}

export function useLiveRates(refetchMs = 5000) {
    return useQuery({
        queryKey: LIVE_RATES_QUERY_KEY,
        queryFn: () => api.analytics.liveRates(),
        refetchInterval: refetchMs,
        refetchIntervalInBackground: false,
        placeholderData: (previousData) => previousData,
    });
}
