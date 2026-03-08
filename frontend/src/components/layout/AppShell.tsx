"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Terminal, Database, Bookmark, Settings, Activity, ChevronRight, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";

type NavItem = {
    name: string;
    href: string;
    hint: string;
    icon: React.ComponentType<{ className?: string }>;
};

const NAV_ITEMS: NavItem[] = [
    { name: "控制台", href: "/", icon: Terminal, hint: "创建与总览" },
    { name: "采集任务", href: "/tasks", icon: Database, hint: "查看运行状态" },
    { name: "断点续传", href: "/checkpoints", icon: Bookmark, hint: "恢复中断任务" },
    { name: "设置", href: "/settings", icon: Settings, hint: "浏览器与账号" },
];

function isActivePath(pathname: string, href: string) {
    return pathname === href || (href !== "/" && pathname.startsWith(href));
}

function getCurrentNav(pathname: string) {
    return NAV_ITEMS.find((item) => isActivePath(pathname, item.href)) ?? NAV_ITEMS[0];
}

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
                        <Link href="/" className="group flex min-w-0 items-center gap-3">
                            <div className="rounded-2xl border border-border/70 bg-background p-2.5 shadow-sm transition-transform group-hover:scale-[1.03]">
                                <Activity className="h-5 w-5 text-primary" />
                            </div>
                            <div className="min-w-0">
                                <p className="text-sm font-semibold tracking-wide text-foreground">X_crawler</p>
                                <p className="text-xs text-muted-foreground">多平台采集控制台</p>
                            </div>
                        </Link>
                    </div>

                    <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-4 py-5">
                        <div className="rounded-[1.5rem] border border-border/60 bg-background/65 p-4 shadow-sm">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">Workspace</p>
                            <p className="mt-2 text-lg font-semibold text-foreground">后台主导航</p>
                            <p className="mt-1 text-sm leading-6 text-muted-foreground">
                                一级菜单控制主要页面，右侧区域通过 App Router 进行无整页刷新切换。
                            </p>
                        </div>

                        <nav className="space-y-2" aria-label="主导航">
                            {NAV_ITEMS.map((item) => {
                                const isActive = isActivePath(pathname, item.href);

                                return (
                                    <Link
                                        key={item.href}
                                        href={item.href}
                                        aria-current={isActive ? "page" : undefined}
                                        className={cn(
                                            "group flex items-center gap-3 rounded-[1.25rem] border px-4 py-3 text-sm transition-all duration-200",
                                            isActive
                                                ? "border-primary/20 bg-primary/10 text-foreground shadow-sm"
                                                : "border-transparent text-muted-foreground hover:border-border/70 hover:bg-background/80 hover:text-foreground",
                                        )}
                                    >
                                        <div
                                            className={cn(
                                                "rounded-xl border border-border/60 bg-card p-2 shadow-sm transition-colors",
                                                isActive && "border-primary/15 bg-primary/12 text-primary",
                                            )}
                                        >
                                            <item.icon className="h-4 w-4" />
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            <p className="font-medium">{item.name}</p>
                                            <p className="truncate text-xs text-muted-foreground">{item.hint}</p>
                                        </div>
                                        <ChevronRight
                                            className={cn(
                                                "h-4 w-4 transition-all duration-200",
                                                isActive ? "text-primary" : "opacity-0 group-hover:opacity-50",
                                            )}
                                        />
                                    </Link>
                                );
                            })}
                        </nav>
                    </div>

                    <div className="border-t border-border/60 px-4 py-4">
                        <div className="rounded-[1.25rem] border border-border/60 bg-background/70 p-4 shadow-sm">
                            <p className="text-xs font-semibold text-foreground">当前分区</p>
                            <p className="mt-1 text-sm text-muted-foreground">{currentNav.name} · {currentNav.hint}</p>
                        </div>
                    </div>
                </aside>

                <div className="flex min-h-screen min-w-0 flex-1 flex-col">
                    <header className="sticky top-0 z-40 border-b border-border/50 bg-background/78 backdrop-blur-xl supports-[backdrop-filter]:bg-background/62">
                        <div className="flex h-16 items-center justify-between px-4 sm:px-6 lg:px-8">
                            <div className="flex min-w-0 items-center gap-3">
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="icon"
                                    className="rounded-xl lg:hidden"
                                    aria-label={mobileNavOpen ? "关闭导航菜单" : "打开导航菜单"}
                                    aria-expanded={mobileNavOpen}
                                    onClick={() => setMobileNavOpen((open) => !open)}
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

                    <nav className="flex-1 space-y-2 overflow-y-auto px-3 py-4" aria-label="移动端主导航">
                        {NAV_ITEMS.map((item) => {
                            const isActive = isActivePath(pathname, item.href);

                            return (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    aria-current={isActive ? "page" : undefined}
                                    className={cn(
                                        "flex items-center gap-3 rounded-[1.25rem] border px-4 py-3 text-sm transition-all duration-200",
                                        isActive
                                            ? "border-primary/20 bg-primary/10 text-foreground shadow-sm"
                                            : "border-transparent text-muted-foreground hover:border-border/70 hover:bg-card hover:text-foreground",
                                    )}
                                >
                                    <div className={cn("rounded-xl border border-border/60 bg-card p-2 shadow-sm", isActive && "text-primary")}>
                                        <item.icon className="h-4 w-4" />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <p className="font-medium">{item.name}</p>
                                        <p className="truncate text-xs text-muted-foreground">{item.hint}</p>
                                    </div>
                                </Link>
                            );
                        })}
                    </nav>

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
