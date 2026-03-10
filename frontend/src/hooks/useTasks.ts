"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";

export const TASKS_QUERY_KEY = ["tasks"] as const;

export function useTasksQuery(refetchMs = 5000) {
    return useQuery({
        queryKey: TASKS_QUERY_KEY,
        queryFn: () => api.tasks.list(false),
        refetchInterval: refetchMs,
        refetchIntervalInBackground: false,
        placeholderData: (previousData) => previousData,
    });
}
