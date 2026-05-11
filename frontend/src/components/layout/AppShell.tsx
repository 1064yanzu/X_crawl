"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { AppShellBrand } from "@/components/layout/AppShellBrand";
import { AppShellNavMenu } from "@/components/layout/AppShellNavMenu";
import { AppShellTopBar } from "@/components/layout/AppShellTopBar";
import { NAV_ITEMS, getCurrentNav } from "@/components/layout/app-shell-config";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

export function AppShell({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const [mobileNavOpen, setMobileNavOpen] = React.useState(false);
    const currentNav = React.useMemo(() => getCurrentNav(pathname), [pathname]);

    React.useEffect(() => {
        setMobileNavOpen(false);
    }, [pathname]);

    React.useEffect(() => {
        if (!mobileNavOpen || typeof document === "undefined") return undefined;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () => {
            document.body.style.overflow = previousOverflow;
        };
    }, [mobileNavOpen]);

    return (
        <div className="relative min-h-screen font-sans text-foreground">
            <div className="mx-auto flex min-h-screen w-full max-w-[1480px]">
                {/* Sidebar — 单条垂直分隔线，全部 typography，无毛玻璃无卡片 */}
                <aside className="sticky top-0 hidden h-screen w-[244px] shrink-0 border-r border-[var(--line)] lg:flex lg:flex-col">
                    <div className="px-7 pt-8 pb-6">
                        <AppShellBrand />
                    </div>

                    <div className="flex flex-1 flex-col gap-8 overflow-y-auto px-4 pb-8">
                        <AppShellNavMenu pathname={pathname} items={NAV_ITEMS} ariaLabel="主导航" />

                        <div className="mt-auto px-3">
                            <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-[color:var(--fg-subtle)]">
                                Issue 01 · 2026
                            </p>
                            <p className="mt-2 font-serif text-[13px] italic leading-6 text-[color:var(--fg-muted)]">
                                &ldquo;A crawler that reads, not just one that fetches.&rdquo;
                            </p>
                        </div>
                    </div>
                </aside>

                <div className="relative flex min-h-screen min-w-0 flex-1 flex-col">
                    <AppShellTopBar
                        currentNav={currentNav}
                        mobileNavOpen={mobileNavOpen}
                        onToggleMobileNav={() => setMobileNavOpen((open) => !open)}
                    />

                    <main
                        id="main-content"
                        className="relative z-10 flex-1 pb-16 pt-10 sm:pt-14"
                        tabIndex={-1}
                    >
                        <div className="px-6 sm:px-10 lg:px-14">{children}</div>
                    </main>
                </div>
            </div>

            {/* 移动端抽屉 */}
            <div
                className={cn(
 "fixed inset-0 z-50 bg-[color:var(--bg)]/70 transition lg:hidden",
                    mobileNavOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0",
                )}
                onClick={() => setMobileNavOpen(false)}
                aria-hidden={!mobileNavOpen}
            >
                <aside
                    className={cn(
 "flex h-full w-[280px] max-w-[80vw] flex-col border-r border-[var(--line)] bg-[var(--bg)] transition-transform duration-300 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
                        mobileNavOpen ? "translate-x-0" : "-translate-x-full",
                    )}
                    onClick={(event) => event.stopPropagation()}
                >
                    <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-5">
                        <AppShellBrand />
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label="关闭导航菜单"
                            onClick={() => setMobileNavOpen(false)}
                        >
                            <X className="h-5 w-5" />
                        </Button>
                    </div>

                    <AppShellNavMenu pathname={pathname} items={NAV_ITEMS} ariaLabel="移动端主导航" mobile />

                    <div className="border-t border-[var(--line)] px-5 py-5">
                        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-[color:var(--fg-subtle)]">
                            当前章节
                        </p>
                        <p className="mt-1 font-serif text-base text-foreground">{currentNav.name}</p>
                        <p className="text-xs text-[color:var(--fg-muted)]">{currentNav.hint}</p>
                    </div>
                </aside>
            </div>
        </div>
    );
}
