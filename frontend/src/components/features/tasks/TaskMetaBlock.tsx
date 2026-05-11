import { cn } from "@/lib/utils";

export function TaskMetaBlock({
    label,
    value,
    compact = false,
}: {
    label: string;
    value: string;
    compact?: boolean;
}) {
    return (
        <div className={cn("border border-border bg-background shadow-sm", compact ? "rounded-md px-3 py-2.5" : "rounded-md px-4 py-3")}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
            <p className={cn("line-clamp-2 font-medium text-foreground", compact ? "mt-0.5 text-[13px]" : "mt-1 text-sm")}>{value}</p>
        </div>
    );
}
