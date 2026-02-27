"use client";
import * as React from "react";
import { api, TaskOut } from "@/services/api";

export interface TaskStreamEvent {
    id?: number;
    ts?: string;
    type: string;
    phase?: string;
    page?: number | null;
    delta_tweets?: number;
    delta_replies?: number;
    status?: string | null;
    risk_state?: string | null;
    meta?: Record<string, unknown>;
}

export function useTaskStream(taskId: string, enabled: boolean) {
    const [task, setTask] = React.useState<TaskOut | null>(null);
    const [events, setEvents] = React.useState<TaskStreamEvent[]>([]);
    const [connected, setConnected] = React.useState(false);
    const [lastMessageAt, setLastMessageAt] = React.useState<number | null>(null);

    React.useEffect(() => {
        if (!enabled || !taskId || typeof window === "undefined" || typeof EventSource === "undefined") {
            setConnected(false);
            return;
        }

        const source = new EventSource(api.tasks.streamUrl(taskId));

        const onSnapshot = (evt: MessageEvent<string>) => {
            try {
                const parsed = JSON.parse(evt.data) as TaskOut;
                setTask(parsed);
                setLastMessageAt(Date.now());
            } catch {
                // ignore malformed payload
            }
        };

        const onAction = (evt: MessageEvent<string>) => {
            try {
                const parsed = JSON.parse(evt.data) as TaskStreamEvent;
                setEvents((prev) => {
                    const merged = [...prev, parsed];
                    return merged.slice(-200);
                });
                setLastMessageAt(Date.now());
            } catch {
                // ignore malformed payload
            }
        };

        const onHeartbeat = () => {
            setLastMessageAt(Date.now());
        };

        source.addEventListener("snapshot", onSnapshot as EventListener);
        source.addEventListener("action", onAction as EventListener);
        source.addEventListener("heartbeat", onHeartbeat as EventListener);
        source.onopen = () => setConnected(true);
        source.onerror = () => setConnected(false);

        return () => {
            source.removeEventListener("snapshot", onSnapshot as EventListener);
            source.removeEventListener("action", onAction as EventListener);
            source.removeEventListener("heartbeat", onHeartbeat as EventListener);
            source.close();
            setConnected(false);
        };
    }, [enabled, taskId]);

    const fallbackPolling = !connected;

    return {
        task,
        events,
        connected,
        fallbackPolling,
        lastMessageAt,
    };
}
