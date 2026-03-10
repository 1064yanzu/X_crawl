import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import type { NavItem } from "@/components/layout/app-shell-config";

export function AppShellTopBar({
    currentNav,
    mobileNavOpen,
    onToggleMobileNav,
}: {
    currentNav: NavItem;
    mobileNavOpen: boolean;
    onToggleMobileNav: () => void;
}) {
    return (
        <header className="sticky top-0 z-30 border-b border-border/50 bg-background/72 backdrop-blur-xl supports-[backdrop-filter]:bg-background/62">
            <div className="flex h-16 items-center justify-between px-4 sm:px-6 lg:px-8">
                <div className="flex min-w-0 items-center gap-3">
                    <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        className="rounded-xl lg:hidden"
                        aria-label={mobileNavOpen ? "关闭导航菜单" : "打开导航菜单"}
                        aria-expanded={mobileNavOpen}
                        onClick={onToggleMobileNav}
                    >
                        {mobileNavOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                    </Button>

                    <div className="min-w-0">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Console</p>
                        <p className="truncate text-sm font-semibold text-foreground sm:text-base">{currentNav.name}</p>
                    </div>
                </div>

                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="hidden rounded-full border border-border/70 bg-card px-3 py-1.5 shadow-sm md:inline-flex">
                        {currentNav.hint}
                    </span>
                    <ThemeToggle />
                </div>
            </div>
        </header>
    );
}
