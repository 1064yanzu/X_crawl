"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
    ArrowUpDown,
    Clock3,
    Database,
    Eye,
    ExternalLink,
    Loader2,
    RefreshCcw,
    Search,
    TerminalSquare,
    Trash2,
    X,
} from "lucide-react";
import { api, TaskOut } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PlatformTabs } from "@/components/ui/platform-tabs";
import { PageHeader } from "@/components/ui/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useTasksQuery } from "@/hooks/useTasks";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { getPlatformsWithAll, getPlatformMeta } from "@/lib/platformRegistry";
import { canResumeTask, formatDateTime, getCoverageSummary, getTaskLastUpdated, getTaskPhase, isTaskActive } from "@/lib/task-ui";
import { TaskStatusBadge } from "@/components/features/task-detail/TaskStatusBadge";

type SortMode = "newest" | "oldest" | "results_desc" | "results_asc" | "status";
type BatchAction = "resume" | "delete" | null;
type DensityMode = "comfortable" | "compact";

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

export default function TasksPage() {
    const { data, isLoading, refetch } = useTasksQuery(5000);
    const tasks = React.useMemo(() => data ?? [], [data]);
    const { push } = useToast();
    const router = useRouter();
    const [resumingId, setResumingId] = React.useState<string | null>(null);
    const [deleteId, setDeleteId] = React.useState<string | null>(null);
    const [activePlatform, setActivePlatform] = React.useState("all");
    const [query, setQuery] = React.useState("");
    const [sortMode, setSortMode] = React.useState<SortMode>("newest");
    const [density, setDensity] = React.useState<DensityMode>("comfortable");
    const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
    const [batchAction, setBatchAction] = React.useState<BatchAction>(null);
    const [confirmBatchDelete, setConfirmBatchDelete] = React.useState(false);
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

    const activeCount = tasks.filter((task) => isTaskActive(task.status)).length;
    const completedCount = tasks.filter((task) => task.status === "done").length;
    const riskCount = tasks.filter((task) => task.risk_state !== "none").length;
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
        const saved = window.localStorage.getItem("tasks-density-mode");
        if (saved === "comfortable" || saved === "compact") {
            setDensity(saved);
        }
    }, []);

    React.useEffect(() => {
        if (typeof window === "undefined") return;
        window.localStorage.setItem("tasks-density-mode", density);
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
        const original = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () => {
            window.removeEventListener("keydown", onKeyDown);
            document.body.style.overflow = original;
        };
    }, [previewTaskId]);

    const selectedSet = React.useMemo(() => new Set(selectedIds), [selectedIds]);
    const selectedTasks = React.useMemo(
        () => searchedTasks.filter((task) => selectedSet.has(task.task_id)),
        [searchedTasks, selectedSet],
    );
    const selectedCount = selectedTasks.length;
    const resumableSelectedTasks = React.useMemo(
        () => selectedTasks.filter((task) => canResumeTask(task.status)),
        [selectedTasks],
    );
    const resumableSelectedCount = resumableSelectedTasks.length;
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

    React.useEffect(() => {
        if (typeof window === "undefined" || searchedTasks.length === 0 || previewTaskId) return;

        const isTypingTarget = (target: EventTarget | null) => {
            if (!(target instanceof HTMLElement)) return false;
            const tagName = target.tagName.toLowerCase();
            return target.isContentEditable || ["input", "textarea", "select", "button"].includes(tagName);
        };

        const moveActive = (offset: number) => {
            const currentIndex = searchedTasks.findIndex((task) => task.task_id === activeTaskId);
            const fallbackIndex = currentIndex >= 0 ? currentIndex : 0;
            const nextIndex = Math.max(0, Math.min(searchedTasks.length - 1, fallbackIndex + offset));
            const nextTaskId = searchedTasks[nextIndex]?.task_id;
            if (!nextTaskId) return;
            setActiveTaskId(nextTaskId);
            document.getElementById(`task-card-${nextTaskId}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
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
                moveActive(1);
                return;
            }

            if (event.key === "k" || event.key === "ArrowUp") {
                event.preventDefault();
                moveActive(-1);
                return;
            }

            if (!activeTaskId) return;

            if (event.key === "Enter") {
                event.preventDefault();
                router.push(`/tasks/${activeTaskId}`);
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
    }, [activeTaskId, previewTaskId, router, searchedTasks, selectedSet, toggleSelectTask]);

    const toggleSelectAllVisible = React.useCallback(() => {
        if (allVisibleSelected) {
            clearSelection();
            return;
        }
        setSelectedIds(visibleIds);
    }, [allVisibleSelected, clearSelection, visibleIds]);

    const handleDelete = async (taskId: string) => {
        try {
            await api.tasks.delete(taskId);
            setSelectedIds((prev) => prev.filter((id) => id !== taskId));
            if (previewTaskId === taskId) setPreviewTaskId(null);
            push({ type: "success", title: "任务已删除" });
            await refetch();
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "删除任务失败" });
        }
    };

    const handleResume = async (taskId: string) => {
        setResumingId(taskId);
        try {
            await api.tasks.resume(taskId);
            setSelectedIds((prev) => prev.filter((id) => id !== taskId));
            push({ type: "success", title: "任务已重新加入队列" });
            await refetch();
        } catch (err) {
            console.error(err);
            push({
                type: "error",
                title: "恢复任务失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setResumingId(null);
        }
    };

    const handleBatchResume = async () => {
        if (resumableSelectedCount === 0) {
            push({ type: "info", title: "选中的任务里没有可继续的项目" });
            return;
        }

        const ids = resumableSelectedTasks.map((task) => task.task_id);
        setBatchAction("resume");
        try {
            const results = await Promise.allSettled(ids.map((taskId) => api.tasks.resume(taskId)));
            const successIds = results
                .map((result, index) => (result.status === "fulfilled" ? ids[index] : null))
                .filter((taskId): taskId is string => Boolean(taskId));
            const failedCount = results.length - successIds.length;

            if (successIds.length > 0) {
                setSelectedIds((prev) => prev.filter((id) => !successIds.includes(id)));
                await refetch();
            }

            if (failedCount === 0) {
                push({ type: "success", title: `已恢复 ${successIds.length} 个任务` });
            } else {
                push({
                    type: successIds.length > 0 ? "info" : "error",
                    title: successIds.length > 0 ? `已恢复 ${successIds.length} 个任务` : "批量恢复失败",
                    description: `仍有 ${failedCount} 个任务未恢复成功，请稍后重试。`,
                });
            }
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "批量恢复失败" });
        } finally {
            setBatchAction(null);
        }
    };

    const handleBatchDelete = async () => {
        if (selectedCount === 0) return;

        const ids = selectedTasks.map((task) => task.task_id);
        setBatchAction("delete");
        try {
            const results = await Promise.allSettled(ids.map((taskId) => api.tasks.delete(taskId)));
            const successIds = results
                .map((result, index) => (result.status === "fulfilled" ? ids[index] : null))
                .filter((taskId): taskId is string => Boolean(taskId));
            const failedCount = results.length - successIds.length;

            if (successIds.length > 0) {
                setSelectedIds((prev) => prev.filter((id) => !successIds.includes(id)));
                if (previewTaskId && successIds.includes(previewTaskId)) setPreviewTaskId(null);
                await refetch();
            }

            if (failedCount === 0) {
                push({ type: "success", title: `已删除 ${successIds.length} 个任务` });
            } else {
                push({
                    type: successIds.length > 0 ? "info" : "error",
                    title: successIds.length > 0 ? `已删除 ${successIds.length} 个任务` : "批量删除失败",
                    description: `仍有 ${failedCount} 个任务未删除成功，请稍后重试。`,
                });
            }
        } catch (err) {
            console.error(err);
            push({ type: "error", title: "批量删除失败" });
        } finally {
            setBatchAction(null);
        }
    };

    return (
        <>
            <div className="space-y-6 pb-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
                <PageHeader
                    eyebrow="Task Center"
                    icon={Database}
                    title="采集队列"
                    description="查看和管理采集任务。"
                    actions={
                        <Link href="/">
                            <Button className="rounded-xl">
                                <TerminalSquare className="mr-2 h-4 w-4" />
                                新建任务
                            </Button>
                        </Link>
                    }
                >
                    <div className="grid gap-3 md:grid-cols-3">
                        <StatCard label="全部任务" value={tasks.length} hint="包含历史记录与当前队列" icon={Database} />
                        <StatCard label="运行中 / 暂停" value={activeCount} hint="需要优先关注的任务" icon={Loader2} tone="primary" />
                        <StatCard label="异常 / 风控" value={riskCount} hint={`累计完成 ${completedCount} 个任务`} icon={Clock3} tone={riskCount > 0 ? "warning" : "success"} />
                    </div>
                </PageHeader>

                <div className="space-y-4 rounded-[1.5rem] border border-border/60 bg-card/90 p-4 shadow-sm backdrop-blur-sm sm:p-5">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                        <div>
                            <h2 className="text-lg font-semibold text-foreground">筛选与排序</h2>
                            
                        </div>
                        <PlatformTabs
                            platforms={getPlatformsWithAll()}
                            value={activePlatform}
                            onChange={setActivePlatform}
                            counts={platformCounts}
                        />
                    </div>

                    <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_220px_auto]">
                        <div className="relative">
                            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                            <input
                                ref={searchInputRef}
                                type="text"
                                value={query}
                                onChange={(event) => setQuery(event.target.value)}
                                placeholder="搜索关键词、任务 ID、状态或最近阶段"
                                className="h-11 w-full rounded-xl border border-input bg-background pl-10 pr-4 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                            />
                        </div>
                        <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-background px-3 shadow-sm">
                            <ArrowUpDown className="h-4 w-4 text-muted-foreground" />
                            <select
                                value={sortMode}
                                onChange={(event) => setSortMode(event.target.value as SortMode)}
                                className="h-11 w-full bg-transparent text-sm focus:outline-none"
                            >
                                <option value="newest">按创建时间（最新优先）</option>
                                <option value="oldest">按创建时间（最早优先）</option>
                                <option value="results_desc">按结果数（高到低）</option>
                                <option value="results_asc">按结果数（低到高）</option>
                                <option value="status">按状态排序</option>
                            </select>
                        </div>
                        <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-background p-1 shadow-sm">
                            <Button
                                type="button"
                                variant={density === "comfortable" ? "default" : "ghost"}
                                size="sm"
                                className="rounded-lg"
                                onClick={() => setDensity("comfortable")}
                            >
                                舒展视图
                            </Button>
                            <Button
                                type="button"
                                variant={density === "compact" ? "default" : "ghost"}
                                size="sm"
                                className="rounded-lg"
                                onClick={() => setDensity("compact")}
                            >
                                紧凑视图
                            </Button>
                        </div>
                    </div>
                </div>

                {searchedTasks.length > 0 ? (
                    <Card className="rounded-[1.5rem] border-border/60 bg-card/90 p-4 shadow-sm backdrop-blur-sm sm:p-5">
                        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                            <div>
                                <h2 className="text-lg font-semibold text-foreground">批量操作</h2>
                                <p className="text-sm text-muted-foreground">
                                    当前筛出 {searchedTasks.length} 个任务，已选择 {selectedCount} 个；其中可继续 {resumableSelectedCount} 个。
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <Button variant="outline" className="rounded-xl" onClick={toggleSelectAllVisible}>
                                    {allVisibleSelected ? "取消全选" : "全选当前结果"}
                                </Button>
                                <Button variant="ghost" className="rounded-xl" onClick={clearSelection} disabled={selectedCount === 0}>
                                    清空选择
                                </Button>
                                <Button
                                    variant="outline"
                                    className="rounded-xl"
                                    onClick={() => void handleBatchResume()}
                                    disabled={resumableSelectedCount === 0 || batchAction !== null}
                                >
                                    {batchAction === "resume" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="mr-1.5 h-3.5 w-3.5" />}
                                    批量继续
                                </Button>
                                <Button
                                    variant="outline"
                                    className="rounded-xl border-red-300 text-red-700 hover:bg-red-50 dark:border-red-500/30 dark:text-red-300 dark:hover:bg-red-500/10"
                                    onClick={() => setConfirmBatchDelete(true)}
                                    disabled={selectedCount === 0 || batchAction !== null}
                                >
                                    {batchAction === "delete" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-1.5 h-3.5 w-3.5" />}
                                    删除选中
                                </Button>
                            </div>
                        </div>
                    </Card>
                ) : null}

                <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_380px] xl:items-start">
                    <div className="min-w-0 space-y-4">
                {isLoading && tasks.length === 0 ? (
                    <div className="space-y-3">
                        {[1, 2, 3].map((item) => (
                            <div key={item} className="rounded-[1.5rem] border border-border/60 bg-card/90 p-5 shadow-sm">
                                <div className="space-y-4">
                                    <div className="flex items-center gap-2">
                                        <Skeleton className="h-6 w-24 rounded-full" />
                                        <Skeleton className="h-6 w-24 rounded-full" />
                                    </div>
                                    <Skeleton className="h-7 w-1/2" />
                                    <div className="grid gap-3 md:grid-cols-4">
                                        {[1, 2, 3, 4].map((meta) => <Skeleton key={meta} className="h-16 w-full" />)}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : searchedTasks.length === 0 ? (
                    <EmptyState
                        icon={Database}
                        title={hasSearch ? "没有匹配的任务" : activePlatform === "all" ? "当前还没有采集任务" : `当前没有 ${getPlatformMeta(activePlatform).label} 任务`}
                        description={hasSearch
                            ? "可以尝试修改关键词、切换平台或更换排序方式。"
                            : activePlatform === "all"
                                ? "从控制台创建第一个采集任务后，这里会开始记录实时状态和历史结果。"
                                : "可以切换回全部平台，或直接创建该平台的新任务。"}
                        action={
                            hasSearch ? (
                                <Button variant="outline" className="rounded-xl" onClick={() => setQuery("")}>清空搜索</Button>
                            ) : activePlatform === "all" ? (
                                <Link href="/">
                                    <Button variant="outline" className="rounded-xl">去创建任务</Button>
                                </Link>
                            ) : (
                                <Button variant="outline" className="rounded-xl" onClick={() => setActivePlatform("all")}>查看全部平台</Button>
                            )
                        }
                    />
                ) : (
                    <div className="grid gap-4">
                        {searchedTasks.map((task) => {
                            const platformMeta = getPlatformMeta(task.platform);
                            const phase = getTaskPhase(task);
                            const lastUpdated = formatDateTime(getTaskLastUpdated(task));
                            const coverage = getCoverageSummary(task.time_coverage as Record<string, unknown> | undefined);
                            const selected = selectedSet.has(task.task_id);

                            return (
                                <Card
                                    id={`task-card-${task.task_id}`}
                                    key={task.task_id}
                                    className={cn(
                                        "overflow-hidden border-border/60 bg-card/90 shadow-sm transition-all",
                                        density === "compact" ? "rounded-[1.25rem]" : "rounded-[1.5rem]",
                                        selected && "border-primary/50 ring-2 ring-primary/10",
                                        activeTaskId === task.task_id && "border-sky-400/60 ring-2 ring-sky-500/15",
                                    )}
                                    onMouseEnter={() => setActiveTaskId(task.task_id)}
                                >
                                    <div className="flex flex-col lg:flex-row">
                                        <Link href={`/tasks/${task.task_id}`} className={cn("flex-1", density === "compact" ? "p-4 sm:p-5" : "p-5 sm:p-6")}>
                                            <div className={cn("flex flex-col", density === "compact" ? "gap-3" : "gap-4")}>
                                                <div className="flex flex-wrap items-center gap-2">
                                                    {activeTaskId === task.task_id ? <span className="rounded-full bg-sky-500/10 px-2.5 py-1 text-[11px] font-medium text-sky-700 dark:text-sky-300">当前焦点</span> : null}
                                                    <span className={cn("inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium", platformMeta.badgeClass)}>
                                                        {platformMeta.label}
                                                    </span>
                                                    <TaskStatusBadge status={task.status} riskState={task.risk_state} size="sm" />
                                                    <code className="rounded-full bg-muted px-2.5 py-1 text-[11px] text-muted-foreground">{task.task_id.slice(0, 8)}</code>
                                                </div>

                                                <div>
                                                    <h3 className={cn("line-clamp-2 font-semibold tracking-tight text-foreground", density === "compact" ? "text-lg" : "text-xl")}>{task.keyword}</h3>
                                                    <p className={cn("line-clamp-2 text-sm text-muted-foreground", density === "compact" ? "mt-1.5 leading-5" : "mt-2 leading-6")}>{phase}</p>
                                                </div>

                                                <div className={cn("grid md:grid-cols-2 xl:grid-cols-4", density === "compact" ? "gap-2" : "gap-3")}>
                                                    <MetaBlock label="结果数" value={`${task.result_count}`} compact={density === "compact"} />
                                                    <MetaBlock label="当前页" value={task.current_page > 0 ? `${task.current_page}` : "--"} compact={density === "compact"} />
                                                    <MetaBlock label="覆盖时间" value={coverage} compact={density === "compact"} />
                                                    <MetaBlock label="最近更新" value={lastUpdated} compact={density === "compact"} />
                                                </div>
                                            </div>
                                        </Link>

                                        <div className={cn("border-t border-border/50 bg-muted/15 lg:border-l lg:border-t-0", density === "compact" ? "p-3 lg:w-[220px]" : "p-4 lg:w-[236px]")}>
                                            <div className={cn("flex h-full flex-col", density === "compact" ? "gap-2.5" : "gap-3")}>
                                                <label className="inline-flex items-center gap-2 self-start rounded-full border border-border/60 bg-card px-3 py-1.5 text-xs font-medium text-foreground shadow-sm">
                                                    <input
                                                        type="checkbox"
                                                        checked={selected}
                                                        onChange={(event) => toggleSelectTask(task.task_id, event.target.checked)}
                                                        className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
                                                    />
                                                    选中此任务
                                                </label>

                                                <div className="w-full rounded-2xl border border-border/60 bg-card px-3 py-3 text-xs text-muted-foreground shadow-sm">
                                                    <p className="font-semibold uppercase tracking-[0.16em]">任务信息</p>
                                                    <p className="mt-2">创建于 {formatDateTime(task.created_at)}</p>
                                                    {task.finished_at ? <p className="mt-1">结束于 {formatDateTime(task.finished_at)}</p> : null}
                                                </div>

                                                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        className="rounded-xl justify-start"
                                                        onClick={() => setPreviewTaskId(task.task_id)}
                                                    >
                                                        <Eye className="mr-1.5 h-3.5 w-3.5" />
                                                        快速预览
                                                    </Button>

                                                    {canResumeTask(task.status) ? (
                                                        <Button
                                                            variant="outline"
                                                            size="sm"
                                                            className="rounded-xl justify-start"
                                                            disabled={resumingId === task.task_id || batchAction !== null}
                                                            onClick={() => void handleResume(task.task_id)}
                                                        >
                                                            {resumingId === task.task_id ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="mr-1.5 h-3.5 w-3.5" />}
                                                            继续
                                                        </Button>
                                                    ) : null}
                                                </div>

                                                <div className="mt-auto flex gap-2 lg:justify-end">
                                                    <Link href={`/tasks/${task.task_id}`} className="flex-1 lg:flex-none">
                                                        <Button variant="ghost" size="sm" className="w-full rounded-xl text-muted-foreground">
                                                            <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                                                            详情
                                                        </Button>
                                                    </Link>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        className="rounded-xl text-muted-foreground hover:text-red-600"
                                                        onClick={() => setDeleteId(task.task_id)}
                                                        disabled={batchAction !== null}
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </Card>
                            );
                        })}
                    </div>
                )}
                    </div>

                    <aside className="hidden xl:block">
                        <div className="sticky top-24">
                            <TaskPreviewPanel
                                task={activePreviewTask}
                                resumingId={resumingId}
                                onResume={(taskId) => void handleResume(taskId)}
                                onDelete={(taskId) => setDeleteId(taskId)}
                            />
                        </div>
                    </aside>
                </div>

                <ConfirmDialog
                    open={Boolean(deleteId)}
                    title="确认删除任务？"
                    description="删除后该任务会从当前列表移除，已导出的文件不受影响。"
                    confirmText="删除"
                    cancelText="取消"
                    onCancel={() => setDeleteId(null)}
                    onConfirm={async () => {
                        if (!deleteId) return;
                        const id = deleteId;
                        setDeleteId(null);
                        await handleDelete(id);
                    }}
                />

                <ConfirmDialog
                    open={confirmBatchDelete}
                    title="确认批量删除所选任务？"
                    description={`当前将删除 ${selectedCount} 个任务。已导出的文件不会受影响，但这些任务会从当前列表移除。`}
                    confirmText="批量删除"
                    cancelText="取消"
                    onCancel={() => setConfirmBatchDelete(false)}
                    onConfirm={async () => {
                        setConfirmBatchDelete(false);
                        await handleBatchDelete();
                    }}
                />
            </div>

            <TaskPreviewDrawer
                task={previewTask}
                resumingId={resumingId}
                onClose={() => setPreviewTaskId(null)}
                onResume={(taskId) => void handleResume(taskId)}
                onDelete={(taskId) => setDeleteId(taskId)}
            />
        </>
    );
}

function MetaBlock({ label, value, compact = false }: { label: string; value: string; compact?: boolean }) {
    return (
        <div className={cn("border border-border/60 bg-background/70 shadow-sm", compact ? "rounded-xl px-3 py-2.5" : "rounded-2xl px-4 py-3")}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
            <p className={cn("line-clamp-2 font-medium text-foreground", compact ? "mt-0.5 text-[13px]" : "mt-1 text-sm")}>{value}</p>
        </div>
    );
}


function TaskPreviewPanel({
    task,
    resumingId,
    onResume,
    onDelete,
}: {
    task: TaskOut | null;
    resumingId: string | null;
    onResume: (taskId: string) => void;
    onDelete: (taskId: string) => void;
}) {
    if (!task) {
        return (
            <Card className="rounded-[1.75rem] border-border/60 bg-card/90 p-5 shadow-sm backdrop-blur-sm">
                <div className="space-y-4">
                    <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Live Preview</p>
                        <h2 className="mt-1 text-xl font-semibold text-foreground">右侧任务预览</h2>
                        <p className="mt-1 text-sm leading-6 text-muted-foreground">选择任务后会在这里显示预览。</p>
                    </div>
                    <div className="rounded-[1.25rem] border border-dashed border-border/70 bg-background/60 p-4 text-sm leading-6 text-muted-foreground">
                        当前没有可预览的任务。你可以先调整平台筛选、搜索条件，或返回控制台创建新的采集任务。
                    </div>
                </div>
            </Card>
        );
    }

    const platformMeta = getPlatformMeta(task.platform);
    const phase = getTaskPhase(task);
    const coverage = getCoverageSummary(task.time_coverage as Record<string, unknown> | undefined);
    const active = isTaskActive(task.status);

    return (
        <Card className="overflow-hidden rounded-[1.75rem] border-border/60 bg-card/90 shadow-sm backdrop-blur-sm">
            <div className="border-b border-border/60 px-5 py-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Live Preview</p>
                <h2 className="mt-1 text-xl font-semibold text-foreground">右侧任务预览</h2>
                <p className="mt-1 text-sm text-muted-foreground">当前任务概览。</p>
            </div>

            <div className="space-y-5 p-5">
                <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                        <span className={cn("inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium", platformMeta.badgeClass)}>{platformMeta.label}</span>
                        <TaskStatusBadge status={task.status} riskState={task.risk_state} size="sm" />
                        {active ? <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">进行中</span> : null}
                    </div>
                    <div>
                        <h3 className="text-2xl font-semibold tracking-tight text-foreground">{task.keyword}</h3>
                        <p className="mt-2 text-sm leading-6 text-muted-foreground">{phase}</p>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-3 text-sm text-muted-foreground shadow-sm">
                        <p>任务 ID：<span className="font-mono text-foreground">{task.task_id}</span></p>
                        <p className="mt-1">最近更新：{formatDateTime(getTaskLastUpdated(task))}</p>
                    </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                    <PreviewStat label="结果数" value={`${task.result_count}`} hint={task.max_count > 0 ? `目标 ${task.max_count}` : "未设上限"} />
                    <PreviewStat label="当前页" value={task.current_page > 0 ? `${task.current_page}` : "--"} hint={task.finished_at ? `结束于 ${formatDateTime(task.finished_at)}` : "仍在持续更新"} />
                    <PreviewStat label="覆盖时间" value={coverage} hint={formatDateTime(task.created_at)} />
                    <PreviewStat label="风控状态" value={task.risk_state === "none" ? "正常" : task.risk_state} hint={task.status === "done" ? "任务已完成" : active ? "建议持续观察" : "可在详情页复盘"} />
                </div>

                <div className="rounded-[1.25rem] border border-border/60 bg-card/90 p-4 shadow-sm">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">快速判断</p>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span className="rounded-full bg-muted px-2.5 py-1">平台 {platformMeta.label}</span>
                        <span className="rounded-full bg-muted px-2.5 py-1">状态 {task.status}</span>
                        <span className="rounded-full bg-muted px-2.5 py-1">结果 {task.result_count}</span>
                        {task.fetch_replies ? <span className="rounded-full bg-muted px-2.5 py-1">已抓评论</span> : null}
                        {task.resumed ? <span className="rounded-full bg-muted px-2.5 py-1">曾恢复过</span> : null}
                    </div>
                </div>
            </div>

            <div className="border-t border-border/60 px-5 py-4">
                <div className="flex flex-col gap-2">
                    <Link href={`/tasks/${task.task_id}`}>
                        <Button className="w-full rounded-xl">
                            <ExternalLink className="mr-1.5 h-4 w-4" />
                            打开完整详情
                        </Button>
                    </Link>
                    <div className="flex gap-2">
                        {canResumeTask(task.status) ? (
                            <Button
                                variant="outline"
                                className="flex-1 rounded-xl"
                                disabled={resumingId === task.task_id}
                                onClick={() => onResume(task.task_id)}
                            >
                                {resumingId === task.task_id ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-1.5 h-4 w-4" />}
                                继续
                            </Button>
                        ) : null}
                        <Button variant="outline" className="flex-1 rounded-xl text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-500/10" onClick={() => onDelete(task.task_id)}>
                            <Trash2 className="mr-1.5 h-4 w-4" />
                            删除
                        </Button>
                    </div>
                </div>
            </div>
        </Card>
    );
}

function TaskPreviewDrawer({
    task,
    resumingId,
    onClose,
    onResume,
    onDelete,
}: {
    task: TaskOut | null;
    resumingId: string | null;
    onClose: () => void;
    onResume: (taskId: string) => void;
    onDelete: (taskId: string) => void;
}) {
    if (!task) return null;

    const platformMeta = getPlatformMeta(task.platform);
    const phase = getTaskPhase(task);
    const coverage = getCoverageSummary(task.time_coverage as Record<string, unknown> | undefined);
    const active = isTaskActive(task.status);

    return (
        <div className="fixed inset-0 z-50">
            <button
                type="button"
                aria-label="关闭预览"
                className="absolute inset-0 bg-background/70 backdrop-blur-sm"
                onClick={onClose}
            />
            <div className="absolute inset-y-0 right-0 w-full max-w-xl border-l border-border/60 bg-background shadow-2xl">
                <div className="flex h-full flex-col">
                    <div className="flex items-start justify-between gap-4 border-b border-border/60 px-5 py-4 sm:px-6">
                        <div className="min-w-0">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Quick Preview</p>
                            <h2 className="mt-1 text-xl font-semibold text-foreground">任务快速预览</h2>
                            <p className="mt-1 text-sm text-muted-foreground">当前任务概览。</p>
                        </div>
                        <Button variant="ghost" size="icon" className="rounded-xl" onClick={onClose}>
                            <X className="h-4 w-4" />
                        </Button>
                    </div>

                    <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-6">
                        <div className="space-y-3">
                            <div className="flex flex-wrap items-center gap-2">
                                <span className={cn("inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium", platformMeta.badgeClass)}>{platformMeta.label}</span>
                                <TaskStatusBadge status={task.status} riskState={task.risk_state} size="sm" />
                                {active ? <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">进行中</span> : null}
                            </div>
                            <div>
                                <h3 className="text-2xl font-semibold tracking-tight text-foreground">{task.keyword}</h3>
                                <p className="mt-2 text-sm leading-6 text-muted-foreground">{phase}</p>
                            </div>
                            <div className="rounded-2xl border border-border/60 bg-card/80 px-4 py-3 text-sm text-muted-foreground shadow-sm">
                                <p>任务 ID：<span className="font-mono text-foreground">{task.task_id}</span></p>
                                <p className="mt-1">最近更新：{formatDateTime(getTaskLastUpdated(task))}</p>
                            </div>
                        </div>

                        <div className="grid gap-3 sm:grid-cols-2">
                            <PreviewStat label="结果数" value={`${task.result_count}`} hint={task.max_count > 0 ? `目标 ${task.max_count}` : "未设上限"} />
                            <PreviewStat label="当前页" value={task.current_page > 0 ? `${task.current_page}` : "--"} hint={task.finished_at ? `结束于 ${formatDateTime(task.finished_at)}` : "仍在持续更新"} />
                            <PreviewStat label="覆盖时间" value={coverage} hint={formatDateTime(task.created_at)} />
                            <PreviewStat label="风控状态" value={task.risk_state === "none" ? "正常" : task.risk_state} hint={task.status === "done" ? "任务已完成" : active ? "建议持续观察" : "可在详情页复盘"} />
                        </div>

                        <div className="rounded-[1.25rem] border border-border/60 bg-card/90 p-4 shadow-sm">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">快速判断</p>
                            <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                                <span className="rounded-full bg-muted px-2.5 py-1">平台 {platformMeta.label}</span>
                                <span className="rounded-full bg-muted px-2.5 py-1">状态 {task.status}</span>
                                <span className="rounded-full bg-muted px-2.5 py-1">结果 {task.result_count}</span>
                                {task.fetch_replies ? <span className="rounded-full bg-muted px-2.5 py-1">已抓评论</span> : null}
                                {task.resumed ? <span className="rounded-full bg-muted px-2.5 py-1">曾恢复过</span> : null}
                            </div>
                        </div>
                    </div>

                    <div className="border-t border-border/60 px-5 py-4 sm:px-6">
                        <div className="flex flex-col gap-2 sm:flex-row">
                            <Link href={`/tasks/${task.task_id}`} className="flex-1">
                                <Button className="w-full rounded-xl">
                                    <ExternalLink className="mr-1.5 h-4 w-4" />
                                    打开完整详情
                                </Button>
                            </Link>
                            {canResumeTask(task.status) ? (
                                <Button
                                    variant="outline"
                                    className="rounded-xl"
                                    disabled={resumingId === task.task_id}
                                    onClick={() => onResume(task.task_id)}
                                >
                                    {resumingId === task.task_id ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-1.5 h-4 w-4" />}
                                    继续
                                </Button>
                            ) : null}
                            <Button variant="outline" className="rounded-xl text-red-700 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-500/10" onClick={() => onDelete(task.task_id)}>
                                <Trash2 className="mr-1.5 h-4 w-4" />
                                删除
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function PreviewStat({ label, value, hint }: { label: string; value: string; hint: string }) {
    return (
        <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-4 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
            <p className="mt-2 text-lg font-semibold text-foreground">{value}</p>
            <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
        </div>
    );
}
