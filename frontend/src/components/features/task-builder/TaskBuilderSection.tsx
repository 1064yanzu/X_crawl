"use client";

import { cn } from "@/lib/utils";

export function SectionTitle({ title, description }: { title: string; description: string }) {
    return (
        <div>
            <h3 className="text-base font-semibold text-foreground">{title}</h3>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>
        </div>
    );
}

export function PlatformButton({
    active,
    label,
    description,
    onClick,
}: {
    active: boolean;
    label: string;
    description: string;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={cn(
                "min-w-[210px] rounded-2xl border px-4 py-3 text-left transition-all duration-200",
                active ? "border-primary/30 bg-primary/8 text-foreground shadow-sm" : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
            )}
        >
            <p className="font-medium">{label}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
        </button>
    );
}

export function BuilderPanelSkeleton({ title }: { title: string }) {
    return (
        <div className="rounded-2xl border border-border/60 bg-card/80 p-4 shadow-sm">
            <div className="space-y-3 animate-pulse">
                <div className="h-5 w-28 rounded bg-muted" />
                <div className="h-9 w-full rounded-xl bg-muted/80" />
                <div className="h-9 w-full rounded-xl bg-muted/80" />
                <p className="text-xs text-muted-foreground">正在加载{title}...</p>
            </div>
        </div>
    );
}
