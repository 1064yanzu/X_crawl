"use client";
import { ListChecks } from "lucide-react";
import { TaskStreamEvent } from "@/hooks/useTaskStream";

export function TaskLiveTimeline({ events }: { events: TaskStreamEvent[] }) {
    if (events.length === 0) {
        return (
            <div className="rounded-xl border border-dashed bg-muted/20 p-4 text-xs text-muted-foreground">
                暂无实时动作事件
            </div>
        );
    }

    const latest = [...events].slice(-12).reverse();
    return (
        <div className="rounded-xl border bg-card shadow-sm">
            <div className="flex items-center gap-2 border-b px-3 py-2 text-sm font-semibold">
                <ListChecks className="h-4 w-4 text-primary" />
                实时动作流
            </div>
            <div className="max-h-72 overflow-y-auto">
                {latest.map((event, idx) => (
                    <div key={`${event.id ?? idx}-${event.ts ?? ""}`} className="border-b px-3 py-2 last:border-b-0">
                        <div className="flex items-center justify-between gap-3 text-xs">
                            <span className="font-medium text-foreground">{event.phase || event.type}</span>
                            <span className="font-mono text-muted-foreground">{event.ts ? new Date(event.ts).toLocaleTimeString() : "--:--:--"}</span>
                        </div>
                        <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
                            <span>type={event.type}</span>
                            {event.page ? <span>page={event.page}</span> : null}
                            {event.delta_tweets ? <span>+tweet {event.delta_tweets}</span> : null}
                            {event.delta_replies ? <span>+reply {event.delta_replies}</span> : null}
                            {event.risk_state && event.risk_state !== "none" ? <span>risk={event.risk_state}</span> : null}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
