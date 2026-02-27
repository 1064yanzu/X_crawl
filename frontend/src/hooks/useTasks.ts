"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";

export function useTasksQuery(refetchMs = 5000) {
    return useQuery({
        queryKey: ["tasks"],
        queryFn: () => api.tasks.list(false),
        refetchInterval: refetchMs,
    });
}
