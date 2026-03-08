import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
    return <div className={cn("animate-pulse rounded-xl bg-muted/50", className)} aria-hidden="true" />;
}
