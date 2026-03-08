import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
    icon: LucideIcon;
    title: string;
    description: string;
    action?: ReactNode;
    className?: string;
}

export function EmptyState({
    icon: Icon,
    title,
    description,
    action,
    className,
}: EmptyStateProps) {
    return (
        <div
            className={cn(
                "flex flex-col items-center justify-center rounded-[1.5rem] border border-dashed border-border/80 bg-muted/20 px-6 py-16 text-center shadow-sm",
                className,
            )}
        >
            <div className="mb-4 rounded-2xl border border-border/60 bg-background/80 p-4 text-muted-foreground shadow-sm">
                <Icon className="h-8 w-8" />
            </div>
            <h3 className="text-lg font-semibold text-foreground">{title}</h3>
            <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{description}</p>
            {action ? <div className="mt-6">{action}</div> : null}
        </div>
    );
}
