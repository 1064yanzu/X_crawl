import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import type { NavItem } from "@/components/layout/app-shell-config";

/**
 * 编辑感顶栏 — 杂志「页眉 (running head)」：
 * 移除毛玻璃；只用一条细线 + 章节信息小字 + 主题切换。
 */
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
        <header className="sticky top-0 z-30 border-b border-[var(--line)] bg-[var(--bg)]">
            <div className="flex h-16 items-center justify-between px-6 sm:px-10 lg:px-14">
                <div className="flex min-w-0 items-center gap-4">
                    <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        className="lg:hidden"
                        aria-label={mobileNavOpen ? "关闭导航菜单" : "打开导航菜单"}
                        aria-expanded={mobileNavOpen}
                        onClick={onToggleMobileNav}
                    >
                        {mobileNavOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                    </Button>

                    <div className="flex min-w-0 items-baseline gap-3">
                        <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-[color:var(--fg-subtle)]">
                            Running head
                        </p>
                        <span aria-hidden className="h-3 w-px bg-[color:var(--line-strong)]" />
                        <p className="truncate font-serif text-[15px] tracking-tight text-foreground">
                            {currentNav.name}
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-4 text-xs text-[color:var(--fg-muted)]">
                    <span className="hidden font-mono text-[10.5px] uppercase tracking-[0.2em] md:inline-flex">
                        {currentNav.hint}
                    </span>
                    <ThemeToggle />
                </div>
            </div>
        </header>
    );
}
