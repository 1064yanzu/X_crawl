import * as React from "react"
import { cn } from "@/lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
    variant?: "default" | "secondary" | "destructive" | "outline" | "success" | "warning"
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
    const variants = {
        default:
 "border-[var(--accent)] bg-[var(--accent-tint)] text-[color:var(--accent-strong)]",
        secondary:
 "border-[var(--line-strong)] bg-[var(--surface-2)] text-foreground",
        destructive:
 "border-[var(--danger)] bg-[var(--danger-tint)] text-[color:var(--danger)]",
        outline:
 "border-[var(--line-strong)] text-[color:var(--fg-muted)]",
        success:
 "border-[var(--ok)] bg-[var(--ok-tint)] text-[color:var(--ok)]",
        warning:
 "border-[var(--warn)] bg-[var(--warn-tint)] text-[color:var(--warn)]",
    }

    return (
        <div
            className={cn(
 "inline-flex items-center gap-1 border px-2 py-[2px] text-[10.5px] font-medium uppercase tracking-[0.14em] transition-colors",
 "[font-variant-numeric:tabular-nums]",
                variants[variant],
                className,
            )}
            {...props}
        />
    )
}

export { Badge }
