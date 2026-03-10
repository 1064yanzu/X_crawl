"use client";

import * as React from "react";
import { useToast } from "@/components/ui/toast";
import { useTaskQuery } from "@/hooks/useTask";
import { useTaskStream, type TaskStreamEvent } from "@/hooks/useTaskStream";

export function useTaskLiveData(
    taskId: string,
    controlling: "pause" | "resume" | "stop" | null,
) {
    const { push } = useToast();
    const stream = useTaskStream(taskId, Boolean(taskId) && !controlling);
    const { data: polledTask, isLoading, refetch } = useTaskQuery(
        taskId,
        Boolean(controlling),
        stream.fallbackPolling || !stream.task,
    );
    const task = stream.task ?? polledTask;
    const fallbackToastShown = React.useRef(false);

    React.useEffect(() => {
        if (stream.fallbackPolling && !fallbackToastShown.current) {
            push({ type: "info", title: "实时通道暂不可用，已自动回退到轮询模式" });
            fallbackToastShown.current = true;
        }

        if (!stream.fallbackPolling) {
            fallbackToastShown.current = false;
        }
    }, [push, stream.fallbackPolling]);

    const latestActionEvent = React.useMemo(() => {
        if (!task?.latest_action || typeof task.latest_action.type !== "string") return null;
        return task.latest_action as unknown as TaskStreamEvent;
    }, [task?.latest_action]);

    return {
        stream,
        task,
        isLoading,
        refetch,
        latestActionEvent,
    };
}
