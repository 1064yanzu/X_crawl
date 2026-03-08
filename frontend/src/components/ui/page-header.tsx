import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
    title: string;
    description: string;
    icon?: LucideIcon;
    eyebrow?: string;
    actions?: ReactNode;
    children?: ReactNode;
    className?: string;
}

export function PageHeader({
    title,
    description,
    icon: Icon,
    eyebrow,
    actions,
    children,
    className,
}: PageHeaderProps) {
    return (
        <div
            className={cn(
                "rounded-[1.75rem] border border-border/60 bg-card/85 p-6 shadow-sm backdrop-blur-sm sm:p-8",
                className,
            )}
        >
            <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
                <div className="space-y-3">
                    {eyebrow ? (
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                            {eyebrow}
                        </p>
                    ) : null}
                    <div className="flex items-start gap-3">
                        {Icon ? (
                            <div className="mt-0.5 rounded-2xl border border-primary/15 bg-primary/10 p-3 text-primary shadow-sm">
                                <Icon className="h-6 w-6" />
                            </div>
                        ) : null}
                        <div className="space-y-2">
                            <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                                {title}
                            </h1>
                            <p className="max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
                                {description}
                            </p>
                        </div>
                    </div>
                </div>

                {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
            </div>

            {children ? <div className="mt-6">{children}</div> : null}
        </div>
    );
}
