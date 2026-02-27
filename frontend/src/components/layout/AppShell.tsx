"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Terminal, Database, Bookmark, Settings, Activity } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
    { name: "控制台", href: "/", icon: Terminal },
    { name: "采集任务", href: "/tasks", icon: Database },
    { name: "断点续传", href: "/checkpoints", icon: Bookmark },
    { name: "设置", href: "/settings", icon: Settings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();

    return (
        <div className="min-h-screen bg-background flex flex-col font-sans">
            {/* Top Navigation - Glassmorphism */}
            <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/70 backdrop-blur-xl supports-[backdrop-filter]:bg-background/40">
                <div className="w-full max-w-[1200px] mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-6">
                        <Link href="/" className="flex items-center gap-2 group">
                            <div className="flex bg-foreground text-background p-1.5 rounded-[10px] shadow-sm group-hover:scale-105 transition-transform">
                                <Activity className="w-5 h-5" />
                            </div>
                            <span className="font-bold text-lg tracking-tight">X_crawler</span>
                        </Link>

                        <nav className="hidden md:flex items-center gap-1 ml-4">
                            {NAV_ITEMS.map((item) => {
                                const isActive = pathname === item.href;
                                return (
                                    <Link
                                        key={item.href}
                                        href={item.href}
                                        className={cn(
                                            "px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 flex items-center gap-2",
                                            isActive
                                                ? "bg-secondary text-secondary-foreground"
                                                : "text-muted-foreground hover:bg-secondary/40 hover:text-foreground"
                                        )}
                                    >
                                        <item.icon className="w-4 h-4" />
                                        {item.name}
                                    </Link>
                                );
                            })}
                        </nav>
                    </div>

                    <div className="flex items-center gap-4">
                        {/* Right side utilities (e.g., Theme Switcher or User Profile could go here) */}
                    </div>
                </div>
            </header>

            {/* Mobile Bottom Navigation (Optional for deeply native feel) */}
            <div className="md:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-border/40 bg-background/80 backdrop-blur-xl supports-[backdrop-filter]:bg-background/60 pb-safe">
                <nav className="flex items-center justify-around h-16 px-2">
                    {NAV_ITEMS.map((item) => {
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={cn(
                                    "flex flex-col items-center justify-center w-full h-full gap-1 transition-colors",
                                    isActive ? "text-foreground" : "text-muted-foreground"
                                )}
                            >
                                <item.icon className={cn("w-5 h-5", isActive && "fill-current/10")} />
                                <span className="text-[10px] font-medium">{item.name}</span>
                            </Link>
                        );
                    })}
                </nav>
            </div>

            {/* Main Content Area */}
            <main id="main-content" className="flex-1 w-full flex flex-col relative pb-20 md:pb-0" tabIndex={-1}>
                <div className="w-full max-w-[1200px] mx-auto flex-1 px-4 sm:px-6 py-6 md:py-10 animate-in fade-in duration-700">
                    {children}
                </div>
            </main>
        </div>
    );
}
