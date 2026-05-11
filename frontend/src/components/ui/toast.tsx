"use client";
import * as React from "react";
import { CheckCircle2, AlertTriangle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error" | "info";

type ToastItem = {
    id: string;
    title: string;
    description?: string;
    type: ToastType;
};

type ToastContextValue = {
    push: (input: Omit<ToastItem, "id">) => void;
};

const ToastContext = React.createContext<ToastContextValue | null>(null);

const TOAST_TTL = 3000;

const typeMeta: Record<ToastType, { icon: React.ReactNode; rule: string }> = {
    success: { icon: <CheckCircle2 className="h-3.5 w-3.5 text-[var(--ok)]" />, rule: "bg-[var(--ok)]" },
    error:   { icon: <AlertTriangle className="h-3.5 w-3.5 text-[var(--danger)]" />, rule: "bg-[var(--danger)]" },
    info:    { icon: <Info className="h-3.5 w-3.5 text-[var(--accent)]" />, rule: "bg-[var(--accent)]" },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = React.useState<ToastItem[]>([]);

    const remove = React.useCallback((id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const push = React.useCallback((input: Omit<ToastItem, "id">) => {
        const id = crypto.randomUUID();
        setToasts((prev) => [...prev, { id, ...input }]);
        setTimeout(() => remove(id), TOAST_TTL);
    }, [remove]);

    return (
        <ToastContext.Provider value={{ push }}>
            {children}
            <div
                aria-live="polite"
                className="pointer-events-none fixed right-6 top-6 z-[100] flex w-[min(92vw,22rem)] flex-col gap-3"
            >
                {toasts.map((toast) => {
                    const meta = typeMeta[toast.type];
                    return (
                        <div
                            key={toast.id}
                            className={cn(
                                "pointer-events-auto relative border border-[var(--line)] bg-[var(--surface)] px-4 py-3",
                                "[box-shadow:0_12px_32px_-12px_oklch(0.15_0.02_60/0.18)]",
                                "animate-in slide-in-from-top-2 fade-in duration-300",
                            )}
                            role="status"
                        >
                            <span aria-hidden className={cn("absolute left-0 top-0 h-full w-[2px]", meta.rule)} />
                            <div className="flex items-start gap-3 pl-2">
                                <div className="mt-0.5 shrink-0">{meta.icon}</div>
                                <div className="min-w-0 flex-1 space-y-1">
                                    <p className="font-serif text-[14px] leading-snug text-foreground">{toast.title}</p>
                                    {toast.description ? (
                                        <p className="text-[12px] leading-5 text-[color:var(--fg-muted)]">{toast.description}</p>
                                    ) : null}
                                </div>
                                <button
                                    type="button"
                                    className="rounded p-1 text-[color:var(--fg-subtle)] transition-colors hover:text-foreground"
                                    onClick={() => remove(toast.id)}
                                    aria-label="关闭提示"
                                >
                                    <X className="h-3 w-3" />
                                </button>
                            </div>
                        </div>
                    );
                })}
            </div>
        </ToastContext.Provider>
    );
}

export function useToast() {
    const ctx = React.useContext(ToastContext);
    if (!ctx) throw new Error("useToast must be used within ToastProvider");
    return ctx;
}
