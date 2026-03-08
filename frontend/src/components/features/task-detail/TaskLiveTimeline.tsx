"use client";
import * as React from "react";
import { ListChecks, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { TaskStreamEvent } from "@/hooks/useTaskStream";

type TimelineFilter = "all" | "risk" | "page" | "delta";

const FILTER_OPTIONS: Array<{ value: TimelineFilter; label: string }> = [
    { value: "all", label: "全部事件" },
    { value: "risk", label: "仅风控" },
    { value: "page", label: "有翻页" },
    { value: "delta", label: "有增量" },
];

function describeEvent(event: TaskStreamEvent) {
    const items: string[] = [];
    if (event.page) items.push(`第 ${event.page} 页`);
    if (event.delta_tweets) items.push(`新增推文 ${event.delta_tweets}`);
    if (event.delta_replies) items.push(`新增回复 ${event.delta_replies}`);
    if (event.risk_state && event.risk_state !== "none") items.push(`风控 ${event.risk_state}`);
    if (event.status) items.push(`状态 ${event.status}`);
    return items.length > 0 ? items.join(" · ") : "等待更多上下文";
}

function matchesFilter(event: TaskStreamEvent, filter: TimelineFilter) {
    if (filter === "risk") return Boolean(event.risk_state && event.risk_state !== "none");
    if (filter === "page") return typeof event.page === "number" && event.page > 0;
    if (filter === "delta") return Boolean((event.delta_tweets ?? 0) > 0 || (event.delta_replies ?? 0) > 0);
    return true;
}

function matchesQuery(event: TaskStreamEvent, query: string) {
    if (!query) return true;
    const haystack = [
        event.phase,
        event.type,
        event.status,
        event.risk_state,
        event.page ? `page ${event.page}` : "",
        event.delta_tweets ? `tweet ${event.delta_tweets}` : "",
        event.delta_replies ? `reply ${event.delta_replies}` : "",
        describeEvent(event),
    ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
    return haystack.includes(query);
}

export function TaskLiveTimeline({ events }: { events: TaskStreamEvent[] }) {
    const [filter, setFilter] = React.useState<TimelineFilter>("all");
    const [query, setQuery] = React.useState("");
    const normalizedQuery = query.trim().toLowerCase();
    const filteredEvents = React.useMemo(
        () => events.filter((event) => matchesFilter(event, filter) && matchesQuery(event, normalizedQuery)),
        [events, filter, normalizedQuery],
    );
    const latest = [...filteredEvents].slice(-24).reverse();

    if (events.length === 0) {
        return (
            <div className="rounded-2xl border border-dashed border-border/80 bg-muted/20 p-4 text-sm text-muted-foreground">
                实时通道已建立，等待第一条动作事件。
            </div>
        );
    }

    return (
        <div className="rounded-2xl border bg-card shadow-sm">
            <div className="border-b border-border/60 px-4 py-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex items-center gap-2 text-sm font-semibold">
                        <ListChecks className="h-4 w-4 text-primary" />
                        实时动作流
                        <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                            共 {events.length} 条 · 命中 {filteredEvents.length} 条
                        </span>
                    </div>
                    <div className="relative w-full lg:max-w-xs">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <input
                            type="text"
                            value={query}
                            onChange={(event) => setQuery(event.target.value)}
                            placeholder="搜索阶段、类型、状态或风控"
                            className="h-10 w-full rounded-xl border border-input bg-background pl-10 pr-4 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary"
                        />
                    </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                    {FILTER_OPTIONS.map((option) => (
                        <Button
                            key={option.value}
                            variant="outline"
                            size="sm"
                            className={cn("rounded-full", filter === option.value && "border-primary bg-primary/8 text-primary")}
                            onClick={() => setFilter(option.value)}
                        >
                            {option.label}
                        </Button>
                    ))}
                </div>
            </div>

            <div className="max-h-96 overflow-y-auto">
                {latest.length === 0 ? (
                    <div className="px-4 py-10 text-center text-sm text-muted-foreground">
                        当前筛选条件下没有匹配事件，试试切换筛选或清空搜索词。
                    </div>
                ) : (
                    latest.map((event, index) => {
                        const hasRisk = Boolean(event.risk_state && event.risk_state !== "none");
                        const hasPage = typeof event.page === "number" && event.page > 0;
                        const hasDelta = (event.delta_tweets ?? 0) > 0 || (event.delta_replies ?? 0) > 0;

                        return (
                            <div key={`${event.id ?? index}-${event.ts ?? ""}`} className="border-b border-border/50 px-4 py-3 last:border-b-0">
                                <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
                                    <span className="font-medium text-foreground">{event.phase || event.type}</span>
                                    <span className="font-mono text-muted-foreground">
                                        {event.ts ? new Date(event.ts).toLocaleTimeString("zh-CN") : "--:--:--"}
                                    </span>
                                </div>
                                <p className="mt-1 text-sm text-muted-foreground">{describeEvent(event)}</p>
                                <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                                    <span className="rounded-full bg-muted px-2 py-1 text-muted-foreground">类型：{event.type}</span>
                                    {hasRisk ? <span className="rounded-full bg-amber-500/10 px-2 py-1 text-amber-700 dark:text-amber-300">风控</span> : null}
                                    {hasPage ? <span className="rounded-full bg-sky-500/10 px-2 py-1 text-sky-700 dark:text-sky-300">翻页</span> : null}
                                    {hasDelta ? <span className="rounded-full bg-emerald-500/10 px-2 py-1 text-emerald-700 dark:text-emerald-300">有增量</span> : null}
                                    {event.status ? <span className="rounded-full bg-muted px-2 py-1 text-muted-foreground">状态：{event.status}</span> : null}
                                </div>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
}
