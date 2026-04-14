"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { api, type TaskQueueItemRequest } from "@/services/api";
import { useToast } from "@/components/ui/toast";

export interface TaskQueueDraft extends TaskQueueItemRequest {
    draft_id: string;
    summary: string;
}

function buildDraftSummary(task: TaskQueueItemRequest) {
    const platformLabel = task.platform === "weibo" ? "微博" : "𝕏";
    const modeLabel = task.product === "Top"
        ? "最热"
        : task.product === "Latest"
            ? "最新"
            : task.product === "Photos"
                ? "图片"
                : "视频";
    const replyLabel = task.fetch_replies ? `${task.reply_depth ?? 2} 层评论` : "仅帖子";
    const dateLabel = task.platform === "weibo" && (task.start_date || task.end_date)
        ? ` · ${task.start_date ?? "--"} ~ ${task.end_date ?? "--"}`
        : "";
    const splitLabel = task.time_split_mode === "on"
        ? ` · 拆分${task.time_split_window_days ?? "?"}天/段`
        : task.time_split_mode === "off"
            ? " · 不拆分"
            : "";
    return `${platformLabel} · ${modeLabel} · ${replyLabel}${dateLabel}${splitLabel}`;
}

export function useTaskQueueBuilder({
    buildPayload,
    resetDraft,
}: {
    buildPayload: () => TaskQueueItemRequest;
    resetDraft: () => void;
}) {
    const router = useRouter();
    const { push } = useToast();
    const [queueName, setQueueName] = React.useState("");
    const [drafts, setDrafts] = React.useState<TaskQueueDraft[]>([]);
    const [submitting, setSubmitting] = React.useState(false);

    const addCurrentDraft = React.useCallback(() => {
        try {
            const payload = buildPayload();
            const draft: TaskQueueDraft = {
                ...payload,
                draft_id: typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
                    ? crypto.randomUUID()
                    : `${Date.now()}-${Math.random()}`,
                summary: buildDraftSummary(payload),
            };
            setDrafts((prev) => [...prev, draft]);
            resetDraft();
            push({ type: "success", title: "已加入任务队列", description: `累计 ${drafts.length + 1} 个草稿。其他参数已保留，直接输入下一个关键词即可。` });
            return true;
        } catch (error) {
            push({
                type: "error",
                title: "加入队列失败",
                description: error instanceof Error ? error.message : String(error),
            });
            return false;
        }
    }, [buildPayload, drafts.length, push, resetDraft]);

    const removeDraft = React.useCallback((draftId: string) => {
        setDrafts((prev) => prev.filter((draft) => draft.draft_id !== draftId));
    }, []);

    const moveDraft = React.useCallback((draftId: string, direction: -1 | 1) => {
        setDrafts((prev) => {
            const index = prev.findIndex((draft) => draft.draft_id === draftId);
            if (index < 0) return prev;
            const nextIndex = index + direction;
            if (nextIndex < 0 || nextIndex >= prev.length) return prev;
            const next = [...prev];
            const [item] = next.splice(index, 1);
            next.splice(nextIndex, 0, item);
            return next;
        });
    }, []);

    const clearDrafts = React.useCallback(() => setDrafts([]), []);

    const submitQueue = React.useCallback(async () => {
        if (drafts.length === 0) {
            push({ type: "error", title: "请先至少加入一个任务" });
            return;
        }
        setSubmitting(true);
        try {
            const tasks = drafts.map((draft) => ({
                keyword: draft.keyword,
                product: draft.product,
                fetch_replies: draft.fetch_replies,
                max_replies_per_tweet: draft.max_replies_per_tweet,
                reply_depth: draft.reply_depth,
                crawl_strategy: draft.crawl_strategy,
                platform: draft.platform,
                start_date: draft.start_date,
                end_date: draft.end_date,
                time_split_mode: draft.time_split_mode,
                time_split_window_days: draft.time_split_window_days,
                time_split_max_segments: draft.time_split_max_segments,
            }));
            const queue = await api.taskQueues.create({
                name: queueName.trim() || undefined,
                tasks,
            });
            setDrafts([]);
            setQueueName("");
            push({
                type: "success",
                title: "任务队列已创建",
                description: `共 ${queue.total_tasks} 个任务，已按顺序开始执行。`,
            });
            router.push("/tasks");
        } catch (error) {
            push({
                type: "error",
                title: "创建任务队列失败",
                description: error instanceof Error ? error.message : String(error),
            });
        } finally {
            setSubmitting(false);
        }
    }, [drafts, push, queueName, router]);

    return {
        queueName,
        setQueueName,
        drafts,
        submitting,
        addCurrentDraft,
        removeDraft,
        moveDraft,
        clearDrafts,
        submitQueue,
    };
}
