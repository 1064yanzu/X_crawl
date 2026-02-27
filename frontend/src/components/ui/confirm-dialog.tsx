"use client";
import * as React from "react";
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
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-md rounded-2xl border bg-card p-5 shadow-xl">
                <div className="flex items-start gap-3">
                    <div className="rounded-full bg-amber-500/15 p-2 text-amber-700">
                        <AlertTriangle className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                        <h3 className="text-base font-semibold">{title}</h3>
                        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
                    </div>
                </div>
                <div className="mt-5 flex items-center justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={onCancel}>
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

