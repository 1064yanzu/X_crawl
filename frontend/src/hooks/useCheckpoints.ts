"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type CheckpointInfo } from "@/services/api";

export const CHECKPOINTS_QUERY_KEY = ["checkpoints"] as const;

export function useCheckpointsQuery() {
    return useQuery({
        queryKey: CHECKPOINTS_QUERY_KEY,
        queryFn: api.checkpoints.list,
        staleTime: 5000,
    });
}

export function useDeleteCheckpointMutation() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (taskId: string) => api.checkpoints.delete(taskId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: CHECKPOINTS_QUERY_KEY });
        },
    });
}

export function useResumeCheckpointMutation() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (checkpoint: CheckpointInfo) =>
            api.search.create({
                keyword: checkpoint.keyword,
                max_count: 0,
                product: checkpoint.product as "Top" | "Latest" | "Photos" | "Videos",
                resume: true,
                task_id: checkpoint.task_id,
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: CHECKPOINTS_QUERY_KEY });
        },
    });
}
