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

/**
 * 空状态 — 杂志专题页的「空白栏」：
 * 左上一道印刷红短线，下面叙事文本。
 */
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
 "relative flex flex-col items-start gap-5 px-2 py-16 sm:px-6",
                className,
            )}
        >
            <span aria-hidden className="block h-[2px] w-10 bg-[var(--accent)]" />
            <div className="flex items-start gap-4">
                <Icon
                    aria-hidden
                    className="mt-1 h-5 w-5 text-[color:var(--fg-subtle)]"
                />
                <div className="max-w-lg space-y-3">
                    <h3 className="font-serif text-[1.5rem] font-medium leading-tight text-foreground">
                        {title}
                    </h3>
                    <p className="text-[14px] leading-7 text-[color:var(--fg-muted)]">
                        {description}
                    </p>
                </div>
            </div>
            {action ? <div className="pl-9">{action}</div> : null}
        </div>
    );
}
