"use client";

import { cn } from "@/lib/utils";

export function SectionTitle({ title, description, eyebrow }: { title: string; description: string; eyebrow?: string }) {
    return (
        <div className="space-y-1.5">
            {eyebrow ? (
                <p className="font-mono text-[10px] uppercase tracking-[0.26em] text-[color:var(--fg-subtle)]">
                    {eyebrow}
                </p>
            ) : null}
            <h3 className="font-serif text-[1.15rem] font-medium leading-tight tracking-tight text-foreground">
                {title}
            </h3>
            <p className="text-[12.5px] leading-6 text-[color:var(--fg-muted)]">{description}</p>
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
                "group relative flex min-w-0 flex-1 items-baseline gap-3 border-b px-1 pb-2 pt-1 text-left",
                "transition-colors duration-200 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
                active
                    ? "border-[var(--accent)] text-foreground"
                    : "border-[var(--line)] text-[color:var(--fg-muted)] hover:border-[var(--fg-muted)] hover:text-foreground",
            )}
        >
            <span className="font-serif text-[15px] tracking-tight whitespace-nowrap">{label}</span>
            <span className="truncate text-[11.5px] leading-5 text-[color:var(--fg-subtle)]">{description}</span>
        </button>
    );
}

export function BuilderPanelSkeleton({ title }: { title: string }) {
    return (
        <div className="space-y-3">
            <div className="h-3 w-20 bg-[var(--surface-2)]" />
            <div className="h-9 w-full bg-[var(--surface-2)]" />
            <div className="h-9 w-full bg-[var(--surface-2)]" />
            <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-[color:var(--fg-subtle)]">
                Loading · {title}
            </p>
        </div>
    );
}
