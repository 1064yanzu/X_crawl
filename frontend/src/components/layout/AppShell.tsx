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
        <div className="min-h-screen bg-background font-sans text-foreground">
            <div className="mx-auto flex min-h-screen w-full max-w-[1600px]">
                <aside className="sticky top-0 hidden h-screen w-[280px] shrink-0 border-r border-border/60 bg-card/70 backdrop-blur-xl lg:flex lg:flex-col">
                    <div className="border-b border-border/60 px-5 py-5">
                        <AppShellBrand />
                    </div>

                    <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-4 py-5">
                        <div className="rounded-[1.5rem] border border-border/60 bg-background/65 p-4 shadow-sm">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">Workspace</p>
                            <p className="mt-2 text-lg font-semibold text-foreground">后台主导航</p>
                            <p className="mt-1 text-sm leading-6 text-muted-foreground">
                                一级菜单控制主要页面，右侧区域通过 App Router 进行无整页刷新切换。
                            </p>
                        </div>

                        <AppShellNavMenu pathname={pathname} items={NAV_ITEMS} ariaLabel="主导航" />
                    </div>
                </aside>

                <div className="flex min-h-screen min-w-0 flex-1 flex-col">
                    <AppShellTopBar
                        currentNav={currentNav}
                        mobileNavOpen={mobileNavOpen}
                        onToggleMobileNav={() => setMobileNavOpen((open) => !open)}
                    />

                    <main id="main-content" className="flex-1 pb-8 pt-6 sm:pt-8" tabIndex={-1}>
                        <div className="px-4 sm:px-6 lg:px-8">{children}</div>
                    </main>
                </div>
            </div>

            <div
                className={cn(
                    "fixed inset-0 z-50 bg-slate-950/35 backdrop-blur-sm transition lg:hidden",
                    mobileNavOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0",
                )}
                onClick={() => setMobileNavOpen(false)}
                aria-hidden={!mobileNavOpen}
            >
                <aside
                    className={cn(
                        "flex h-full w-[280px] max-w-[80vw] flex-col border-r border-border/60 bg-background/95 shadow-2xl transition-transform duration-200",
                        mobileNavOpen ? "translate-x-0" : "-translate-x-full",
                    )}
                    onClick={(event) => event.stopPropagation()}
                >
                    <div className="flex items-center justify-between border-b border-border/60 px-4 py-4">
                        <div>
                            <p className="text-sm font-semibold text-foreground">X_crawler</p>
                            <p className="text-xs text-muted-foreground">后台主导航</p>
                        </div>
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="rounded-xl"
                            aria-label="关闭导航菜单"
                            onClick={() => setMobileNavOpen(false)}
                        >
                            <X className="h-5 w-5" />
                        </Button>
                    </div>

                    <AppShellNavMenu pathname={pathname} items={NAV_ITEMS} ariaLabel="移动端主导航" mobile />

                    <div className="border-t border-border/60 px-4 py-4">
                        <div className="rounded-[1.25rem] border border-border/60 bg-card/70 p-4 shadow-sm">
                            <p className="text-xs font-semibold text-foreground">当前分区</p>
                            <p className="mt-1 text-sm text-muted-foreground">{currentNav.name} · {currentNav.hint}</p>
                        </div>
                    </div>
                </aside>
            </div>
        </div>
    );
}
