"use client";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

type ConfirmDialogProps = {
    open: boolean;
    title: string;
    description?: string;
    confirmText?: string;
    cancelText?: string;
    onConfirm: () => void;
    onCancel: () => void;
};

export function ConfirmDialog({
    open,
    title,
    description,
    confirmText = "确认",
    cancelText = "取消",
    onConfirm,
    onCancel,
}: ConfirmDialogProps) {
    if (!open) return null;
    return (
        <div
            className="fixed inset-0 z-[90] flex items-center justify-center bg-[color:var(--bg)]/70 p-4 animate-in fade-in duration-200"
            onClick={onCancel}
        >
            <div
                className="relative w-full max-w-md border border-[var(--line)] bg-[var(--surface)] p-7 [box-shadow:0_24px_64px_-20px_oklch(0.15_0.02_60/0.25)] animate-in zoom-in-95 fade-in duration-200"
                onClick={(e) => e.stopPropagation()}
            >
                <span aria-hidden className="absolute left-0 top-0 h-full w-[2px] bg-[var(--danger)]" />
                <div className="flex items-start gap-4 pl-3">
                    <AlertTriangle className="mt-1 h-4 w-4 shrink-0 text-[var(--danger)]" />
                    <div className="min-w-0 space-y-2">
                        <p className="font-mono text-[10px] uppercase tracking-[0.26em] text-[color:var(--fg-subtle)]">
                            Confirmation
                        </p>
                        <h3 className="font-serif text-[1.25rem] font-medium leading-tight text-foreground">
                            {title}
                        </h3>
                        {description ? (
                            <p className="text-[13px] leading-6 text-[color:var(--fg-muted)]">{description}</p>
                        ) : null}
                    </div>
                </div>
                <div className="mt-6 flex items-center justify-end gap-3 pl-3">
                    <Button variant="ghost" size="sm" onClick={onCancel}>
                        {cancelText}
                    </Button>
                    <Button variant="destructive" size="sm" onClick={onConfirm}>
                        {confirmText}
                    </Button>
                </div>
            </div>
        </div>
    );
}
