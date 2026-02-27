"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";

export function useTaskQuery(taskId: string, controlling: boolean, pollingEnabled = true) {
    return useQuery({
        queryKey: ["task", taskId],
        queryFn: async () => {
            const lightTask = await api.search.get(taskId, false);
            const status = lightTask.status;
            if (status === "running" || status === "pending" || status === "paused") {
                return lightTask;
            }
            return api.search.get(taskId, true);
        },
        enabled: Boolean(taskId),
        refetchInterval: (query) => {
            if (!pollingEnabled) return false;
            const status = query.state.data?.status;
            if (controlling) return false;
            return status === "running" || status === "pending" || status === "paused" ? 2000 : false;
        },
    });
}
