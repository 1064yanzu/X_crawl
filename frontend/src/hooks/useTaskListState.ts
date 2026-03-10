"use client";

import * as React from "react";
import type { TaskOut } from "@/services/api";
import { canResumeTask, getTaskPhase, isTaskActive } from "@/lib/task-ui";

const DENSITY_STORAGE_KEY = "tasks-density-mode";

export type SortMode = "newest" | "oldest" | "results_desc" | "results_asc" | "status";
export type DensityMode = "comfortable" | "compact";

function sortTasks<T extends { created_at: string; result_count: number; status: string }>(tasks: T[], mode: SortMode) {
    const sorted = [...tasks];
    sorted.sort((left, right) => {
        if (mode === "oldest") return new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
        if (mode === "results_desc") return right.result_count - left.result_count;
        if (mode === "results_asc") return left.result_count - right.result_count;
        if (mode === "status") return left.status.localeCompare(right.status, "zh-CN");
        return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    });
    return sorted;
}

export function useTaskListState(tasks: TaskOut[], onOpenTask: (taskId: string) => void) {
    const [activePlatform, setActivePlatform] = React.useState("all");
    const [query, setQuery] = React.useState("");
    const [sortMode, setSortMode] = React.useState<SortMode>("newest");
    const [density, setDensity] = React.useState<DensityMode>("comfortable");
    const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
    const [previewTaskId, setPreviewTaskId] = React.useState<string | null>(null);
    const [activeTaskId, setActiveTaskId] = React.useState<string | null>(null);
    const searchInputRef = React.useRef<HTMLInputElement | null>(null);

    const searchedTasks = React.useMemo(() => {
        const keyword = query.trim().toLowerCase();
        const platformFiltered = activePlatform === "all"
            ? tasks
            : tasks.filter((task) => (task.platform ?? "x") === activePlatform);

        if (!keyword) return sortTasks(platformFiltered, sortMode);

        const matched = platformFiltered.filter((task) => {
            const phase = getTaskPhase(task).toLowerCase();
            return [task.keyword, task.task_id, task.status, phase]
                .join(" ")
                .toLowerCase()
                .includes(keyword);
        });

        return sortTasks(matched, sortMode);
    }, [activePlatform, query, sortMode, tasks]);

    const platformCounts = React.useMemo(() => {
        const counts: Record<string, number> = { all: tasks.length };
        for (const task of tasks) {
            const platform = task.platform ?? "x";
            counts[platform] = (counts[platform] ?? 0) + 1;
        }
        return counts;
    }, [tasks]);

    const activeCount = React.useMemo(() => tasks.filter((task) => isTaskActive(task.status)).length, [tasks]);
    const completedCount = React.useMemo(() => tasks.filter((task) => task.status === "done").length, [tasks]);
    const riskCount = React.useMemo(() => tasks.filter((task) => task.risk_state !== "none").length, [tasks]);
    const hasSearch = query.trim().length > 0;
    const visibleIds = React.useMemo(() => searchedTasks.map((task) => task.task_id), [searchedTasks]);
    const visibleIdSet = React.useMemo(() => new Set(visibleIds), [visibleIds]);
    const previewTask = React.useMemo(
        () => tasks.find((task) => task.task_id === previewTaskId) ?? null,
        [previewTaskId, tasks],
    );
    const activePreviewTask = React.useMemo(
        () => searchedTasks.find((task) => task.task_id === activeTaskId) ?? searchedTasks[0] ?? null,
        [activeTaskId, searchedTasks],
    );

    React.useEffect(() => {
        setSelectedIds((prev) => prev.filter((id) => visibleIdSet.has(id)));
    }, [visibleIdSet]);

    React.useEffect(() => {
        if (searchedTasks.length === 0) {
            setActiveTaskId(null);
            return;
        }
        if (!activeTaskId || !searchedTasks.some((task) => task.task_id === activeTaskId)) {
            setActiveTaskId(searchedTasks[0].task_id);
        }
    }, [activeTaskId, searchedTasks]);

    React.useEffect(() => {
        if (typeof window === "undefined") return;
        const saved = window.localStorage.getItem(DENSITY_STORAGE_KEY);
        if (saved === "comfortable" || saved === "compact") {
            setDensity(saved);
        }
    }, []);

    React.useEffect(() => {
        if (typeof window === "undefined") return;
        window.localStorage.setItem(DENSITY_STORAGE_KEY, density);
    }, [density]);

    React.useEffect(() => {
        if (previewTaskId && !tasks.some((task) => task.task_id === previewTaskId)) {
            setPreviewTaskId(null);
        }
    }, [previewTaskId, tasks]);

    React.useEffect(() => {
        if (!previewTaskId) return;

        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") setPreviewTaskId(null);
        };

        window.addEventListener("keydown", onKeyDown);
        const originalOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";

        return () => {
            window.removeEventListener("keydown", onKeyDown);
            document.body.style.overflow = originalOverflow;
        };
    }, [previewTaskId]);

    const selectedSet = React.useMemo(() => new Set(selectedIds), [selectedIds]);
    const selectedTasks = React.useMemo(
        () => searchedTasks.filter((task) => selectedSet.has(task.task_id)),
        [searchedTasks, selectedSet],
    );
    const resumableSelectedTasks = React.useMemo(
        () => selectedTasks.filter((task) => canResumeTask(task.status)),
        [selectedTasks],
    );
    const allVisibleSelected = searchedTasks.length > 0 && searchedTasks.every((task) => selectedSet.has(task.task_id));

    const clearSelection = React.useCallback(() => setSelectedIds([]), []);

    const toggleSelectTask = React.useCallback((taskId: string, checked: boolean) => {
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (checked) next.add(taskId);
            else next.delete(taskId);
            return Array.from(next);
        });
    }, []);

    const moveActiveTask = React.useCallback((offset: number) => {
        const currentIndex = searchedTasks.findIndex((task) => task.task_id === activeTaskId);
        const fallbackIndex = currentIndex >= 0 ? currentIndex : 0;
        const nextIndex = Math.max(0, Math.min(searchedTasks.length - 1, fallbackIndex + offset));
        const nextTaskId = searchedTasks[nextIndex]?.task_id;

        if (!nextTaskId) return;

        setActiveTaskId(nextTaskId);
        document.getElementById(`task-card-${nextTaskId}`)?.scrollIntoView({
            block: "nearest",
            behavior: "smooth",
        });
    }, [activeTaskId, searchedTasks]);

    React.useEffect(() => {
        if (typeof window === "undefined" || searchedTasks.length === 0 || previewTaskId) return;

        const isTypingTarget = (target: EventTarget | null) => {
            if (!(target instanceof HTMLElement)) return false;
            const tagName = target.tagName.toLowerCase();
            return target.isContentEditable || ["input", "textarea", "select", "button"].includes(tagName);
        };

        const onKeyDown = (event: KeyboardEvent) => {
            if (isTypingTarget(event.target)) return;

            if (event.key === "/") {
                event.preventDefault();
                searchInputRef.current?.focus();
                searchInputRef.current?.select();
                return;
            }

            if (event.key === "j" || event.key === "ArrowDown") {
                event.preventDefault();
                moveActiveTask(1);
                return;
            }

            if (event.key === "k" || event.key === "ArrowUp") {
                event.preventDefault();
                moveActiveTask(-1);
                return;
            }

            if (!activeTaskId) return;

            if (event.key === "Enter") {
                event.preventDefault();
                onOpenTask(activeTaskId);
                return;
            }

            if (event.key.toLowerCase() === "v") {
                event.preventDefault();
                setPreviewTaskId(activeTaskId);
                return;
            }

            if (event.key.toLowerCase() === "x") {
                event.preventDefault();
                toggleSelectTask(activeTaskId, !selectedSet.has(activeTaskId));
            }
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [activeTaskId, moveActiveTask, onOpenTask, previewTaskId, searchedTasks.length, selectedSet, toggleSelectTask]);

    const toggleSelectAllVisible = React.useCallback(() => {
        if (allVisibleSelected) {
            clearSelection();
            return;
        }
        setSelectedIds(visibleIds);
    }, [allVisibleSelected, clearSelection, visibleIds]);

    return {
        searchInputRef,
        activePlatform,
        setActivePlatform,
        query,
        setQuery,
        sortMode,
        setSortMode,
        density,
        setDensity,
        searchedTasks,
        platformCounts,
        activeCount,
        completedCount,
        riskCount,
        hasSearch,
        previewTaskId,
        previewTask,
        activeTaskId,
        setActiveTaskId,
        activePreviewTask,
        selectedSet,
        selectedTasks,
        selectedCount: selectedTasks.length,
        resumableSelectedTasks,
        resumableSelectedCount: resumableSelectedTasks.length,
        allVisibleSelected,
        clearSelection,
        toggleSelectTask,
        toggleSelectAllVisible,
        openPreview: setPreviewTaskId,
        closePreview: () => setPreviewTaskId(null),
    };
}
