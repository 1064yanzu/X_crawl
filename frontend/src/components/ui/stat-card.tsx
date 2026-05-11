import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardProps {
    label: string;
    value: ReactNode;
    hint?: string;
    icon?: LucideIcon;
    tone?: "default" | "primary" | "success" | "warning" | "danger";
    className?: string;
}

/**
 * 统计单元 — 「数据栏」风格：
 * 顶部小字签 + 衬线大数字 + 底部一行 hint。
 * 多个 StatCard 排在一起靠 `divide-x` 的细线分隔，构成「报头摘要」。
 */
const toneIconClass = {
    default: "text-[color:var(--fg-muted)]",
    primary: "text-[var(--accent)]",
    success: "text-[var(--ok)]",
    warning: "text-[var(--warn)]",
    danger: "text-[var(--danger)]",
} as const;

const toneRuleClass = {
    default: "bg-[var(--line)]",
    primary: "bg-[var(--accent)]",
    success: "bg-[var(--ok)]",
    warning: "bg-[var(--warn)]",
    danger: "bg-[var(--danger)]",
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
        <div className={cn("group relative flex flex-col gap-3 px-5 py-4", className)}>
            <span
                aria-hidden
                className={cn("absolute left-5 top-0 h-[2px] w-6", toneRuleClass[tone])}
            />
            <div className="flex items-center justify-between">
                <p className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-[color:var(--fg-muted)]">
                    {label}
                </p>
                {Icon ? <Icon className={cn("h-3.5 w-3.5", toneIconClass[tone])} aria-hidden /> : null}
            </div>
            <div className="numeric font-serif text-[2.1rem] font-medium leading-none tracking-tight text-foreground">
                {value}
            </div>
            {hint ? (
                <p className="text-[12px] leading-5 text-[color:var(--fg-subtle)]">{hint}</p>
            ) : null}
        </div>
    );
}

/** 一组 StatCard 的容器，用细线分隔，构成报头摘要带。 */
export function StatCardGroup({
    children,
    className,
}: {
    children: ReactNode;
    className?: string;
}) {
    return (
        <div
            className={cn(
 "grid grid-cols-1 divide-y divide-[var(--line)] border-y border-[var(--line)] sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4",
                className,
            )}
        >
            {children}
        </div>
    );
}
