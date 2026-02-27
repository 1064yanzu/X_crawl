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

function typeIcon(type: ToastType) {
    if (type === "success") return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
    if (type === "error") return <AlertTriangle className="h-4 w-4 text-red-600" />;
    return <Info className="h-4 w-4 text-blue-600" />;
}

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
            <div aria-live="polite" className="pointer-events-none fixed right-4 top-4 z-[100] flex w-[min(92vw,24rem)] flex-col gap-2">
                {toasts.map((toast) => (
                    <div
                        key={toast.id}
                        className={cn(
                            "pointer-events-auto rounded-xl border bg-card/95 p-3 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-card/80",
                            "animate-in slide-in-from-top-2 fade-in duration-200",
                        )}
                        role="status"
                    >
                        <div className="flex items-start gap-2">
                            <div className="mt-0.5 shrink-0">{typeIcon(toast.type)}</div>
                            <div className="min-w-0 flex-1">
                                <p className="text-sm font-semibold">{toast.title}</p>
                                {toast.description && <p className="mt-0.5 text-xs text-muted-foreground">{toast.description}</p>}
                            </div>
                            <button
                                type="button"
                                className="rounded p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground"
                                onClick={() => remove(toast.id)}
                                aria-label="关闭提示"
                            >
                                <X className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
}

export function useToast() {
    const ctx = React.useContext(ToastContext);
    if (!ctx) throw new Error("useToast must be used within ToastProvider");
    return ctx;
}

