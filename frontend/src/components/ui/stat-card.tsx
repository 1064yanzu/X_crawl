import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardProps {
    label: string;
    value: ReactNode;
    hint?: string;
    icon?: LucideIcon;
    tone?: "default" | "primary" | "success" | "warning";
    className?: string;
}

const toneClassMap = {
    default: "bg-background text-foreground border-border/70",
    primary: "bg-blue-500/8 text-foreground border-blue-500/15",
    success: "bg-emerald-500/8 text-foreground border-emerald-500/15",
    warning: "bg-amber-500/8 text-foreground border-amber-500/15",
} as const;

export function StatCard({
    label,
    value,
    hint,
    icon: Icon,
    tone = "default",
    className,
}: StatCardProps) {
    return (
        <div
            className={cn(
                "rounded-2xl border px-4 py-4 shadow-sm transition-all duration-200",
                toneClassMap[tone],
                className,
            )}
        >
            <div className="flex items-start justify-between gap-3">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        {label}
                    </p>
                    <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
                    {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
                </div>
                {Icon ? (
                    <div className="rounded-xl border border-border/60 bg-background/70 p-2 text-muted-foreground">
                        <Icon className="h-4 w-4" />
                    </div>
                ) : null}
            </div>
        </div>
    );
}
