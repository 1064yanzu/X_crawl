import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { type NavItem, isActivePath } from "@/components/layout/app-shell-config";

export function AppShellNavMenu({
    pathname,
    items,
    ariaLabel,
    mobile = false,
}: {
    pathname: string;
    items: NavItem[];
    ariaLabel: string;
    mobile?: boolean;
}) {
    return (
        <nav className={cn("space-y-2", mobile && "flex-1 overflow-y-auto px-3 py-4")} aria-label={ariaLabel}>
            {items.map((item) => {
                const isActive = isActivePath(pathname, item.href);
                const Icon = item.icon;

                return (
                    <Link
                        key={item.href}
                        href={item.href}
                        aria-current={isActive ? "page" : undefined}
                        className={cn(
                            "group flex items-center gap-3 rounded-[1.25rem] border px-4 py-3 text-sm transition-all duration-200",
                            isActive
                                ? "border-primary/20 bg-primary/10 text-foreground shadow-sm"
                                : mobile
                                    ? "border-transparent text-muted-foreground hover:border-border/70 hover:bg-card hover:text-foreground"
                                    : "border-transparent text-muted-foreground hover:border-border/70 hover:bg-background/80 hover:text-foreground",
                        )}
                    >
                        <div
                            className={cn(
                                "rounded-xl border border-border/60 bg-card p-2 shadow-sm transition-colors",
                                isActive && "border-primary/15 bg-primary/12 text-primary",
                            )}
                        >
                            <Icon className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                            <p className="font-medium">{item.name}</p>
                            <p className="truncate text-xs text-muted-foreground">{item.hint}</p>
                        </div>
                        {!mobile ? (
                            <ChevronRight
                                className={cn(
                                    "h-4 w-4 transition-all duration-200",
                                    isActive ? "translate-x-0 text-primary" : "-translate-x-1 opacity-0 group-hover:translate-x-0 group-hover:opacity-100",
                                )}
                            />
                        ) : null}
                    </Link>
                );
            })}
        </nav>
    );
}
