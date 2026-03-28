import * as React from "react";
import { ArrowUpDown, Keyboard, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PlatformTabs } from "@/components/ui/platform-tabs";
import { getPlatformsWithAll } from "@/lib/platformRegistry";
import type { DensityMode, SortMode } from "@/hooks/useTaskListState";

const SHORTCUTS = ["/ 搜索", "J/K 切换", "V 预览", "X 选择", "Enter 详情"];

export function TaskFiltersBar({
    activePlatform,
    onPlatformChange,
    platformCounts,
    searchInputRef,
    query,
    onQueryChange,
    sortMode,
    onSortModeChange,
    density,
    onDensityChange,
}: {
    activePlatform: string;
    onPlatformChange: (platformId: string) => void;
    platformCounts: Record<string, number>;
    searchInputRef: React.RefObject<HTMLInputElement | null>;
    query: string;
    onQueryChange: (value: string) => void;
    sortMode: SortMode;
    onSortModeChange: (value: SortMode) => void;
    density: DensityMode;
    onDensityChange: (value: DensityMode) => void;
}) {
    return (
        <div className="space-y-4 rounded-[1.5rem] border border-border/60 bg-card/90 p-4 shadow-sm backdrop-blur-sm sm:p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                    <h2 className="text-lg font-semibold text-foreground">筛选与排序</h2>
                    <p className="text-sm text-muted-foreground">平台、搜索、视图密度和常用快捷键都集中在这里。</p>
                </div>
                <PlatformTabs
                    platforms={getPlatformsWithAll()}
                    value={activePlatform}
                    onChange={onPlatformChange}
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
                        onChange={(event) => onQueryChange(event.target.value)}
                        placeholder="搜索关键词、任务 ID、状态或最近阶段"
                        className="h-11 w-full rounded-xl border border-input bg-background pl-10 pr-4 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                </div>

                <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-background px-3 shadow-sm">
                    <ArrowUpDown className="h-4 w-4 text-muted-foreground" />
                    <select
                        value={sortMode}
                        onChange={(event) => onSortModeChange(event.target.value as SortMode)}
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
                    <Button type="button" variant={density === "comfortable" ? "default" : "ghost"} size="sm" className="rounded-lg" onClick={() => onDensityChange("comfortable")}>
                        舒展
                    </Button>
                    <Button type="button" variant={density === "compact" ? "default" : "ghost"} size="sm" className="rounded-lg" onClick={() => onDensityChange("compact")}>
                        紧凑
                    </Button>
                    <Button type="button" variant={density === "mini" ? "default" : "ghost"} size="sm" className="rounded-lg" onClick={() => onDensityChange("mini")}>
                        极简
                    </Button>
                </div>
            </div>

            <div className="flex flex-col gap-3 rounded-[1.25rem] border border-border/60 bg-background/65 px-4 py-3 text-sm text-muted-foreground lg:flex-row lg:items-center lg:justify-between">
                <div className="flex items-center gap-2 font-medium text-foreground">
                    <Keyboard className="h-4 w-4 text-primary" />
                    键盘导航
                </div>
                <div className="flex flex-wrap gap-2">
                    {SHORTCUTS.map((shortcut) => (
                        <span key={shortcut} className="rounded-full bg-muted px-2.5 py-1 text-xs">
                            {shortcut}
                        </span>
                    ))}
                </div>
            </div>
        </div>
    );
}
