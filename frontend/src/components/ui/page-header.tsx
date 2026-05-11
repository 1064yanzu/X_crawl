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

/**
 * PageHeader — 杂志页头风格：
 * 印刷红短线 + 章节小字 + 衬线大标题 + 描述 + 细线收尾。
 */
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
        <header className={cn("relative pt-2", className)}>
            <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
                <div className="max-w-3xl space-y-5">
                    {eyebrow ? (
                        <div className="flex items-center gap-3">
                            <span
                                aria-hidden
                                className="block h-[2px] w-7 bg-[var(--accent)]"
                            />
                            <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-[color:var(--fg-muted)]">
                                {eyebrow}
                            </p>
                        </div>
                    ) : null}

                    <div className="flex items-start gap-4">
                        {Icon ? (
                            <Icon
                                aria-hidden
                                className="mt-2 h-5 w-5 shrink-0 text-[var(--accent)]"
                            />
                        ) : null}
                        <div className="space-y-3">
                            <h1 className="font-serif text-[2.4rem] font-medium leading-[1.08] tracking-[-0.02em] text-foreground sm:text-[3rem]">
                                {title}
                            </h1>
                            <p className="max-w-2xl text-[15px] leading-7 text-[color:var(--fg-muted)]">
                                {description}
                            </p>
                        </div>
                    </div>
                </div>

                {actions ? (
                    <div className="flex shrink-0 items-center gap-2 lg:pb-1">{actions}</div>
                ) : null}
            </div>

            {children ? <div className="mt-8">{children}</div> : null}

            <hr className="rule-editorial mt-8" />
        </header>
    );
}
