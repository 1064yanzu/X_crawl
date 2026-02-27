"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";

export function useHealthQuery() {
    return useQuery({
        queryKey: ["health"],
        queryFn: api.health.check,
        refetchInterval: 30000,
        retry: 0,
    });
}

