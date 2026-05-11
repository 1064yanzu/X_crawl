import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
    return (
        <div
            className={cn(
 "relative overflow-hidden bg-[color:var(--surface-2)]",
 "before:absolute before:inset-0 before:-translate-x-full",
 "before:bg-gradient-to-r before:from-transparent",
 "before:via-[color:var(--surface-sunk)] before:to-transparent",
 "before:animate-[shimmer_1.6s_cubic-bezier(0.22,1,0.36,1)_infinite]",
                className,
            )}
            aria-hidden="true"
        />
    );
}
