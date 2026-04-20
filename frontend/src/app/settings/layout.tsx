"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, Globe, Settings, Twitter, Wrench, Youtube } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { cn } from "@/lib/utils";

type SettingsTab = {
    id: string;
    label: string;
    href: string;
    icon: LucideIcon;
    desc: string;
    color: string;
};

const SETTINGS_TABS: SettingsTab[] = [
    {
        id: "general",
        label: "通用设置",
        href: "/settings",
        icon: Wrench,
        desc: "浏览器、引擎参数、代理与归档",
        color: "text-foreground",
    },
    {
        id: "x",
        label: "𝕏 Twitter",
        href: "/settings/x",
        icon: Twitter,
        desc: "X 平台 Cookie 与账号池管理",
        color: "text-blue-600 dark:text-blue-400",
    },
    {
        id: "weibo",
        label: "微博",
        href: "/settings/weibo",
        icon: Globe,
        desc: "微博凭证与平台专属配置",
        color: "text-orange-500 dark:text-orange-400",
    },
    {
        id: "youtube",
        label: "YouTube",
        href: "/settings/youtube",
        icon: Youtube,
        desc: "YouTube API Key 池与配额监控",
        color: "text-red-600 dark:text-red-400",
    },
];

function getActiveTab(pathname: string): SettingsTab {
    if (pathname === "/settings/x") return SETTINGS_TABS[1];
    if (pathname === "/settings/weibo") return SETTINGS_TABS[2];
    if (pathname === "/settings/youtube") return SETTINGS_TABS[3];
    return SETTINGS_TABS[0];
}

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const currentTab = getActiveTab(pathname);

    return (
        <div className="space-y-6 pb-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
            <PageHeader
                eyebrow="Settings"
                icon={Settings}
                title="系统设置"
                description="管理系统与平台配置。"
                actions={
                    <Link href="/">
                        <Button variant="outline" className="rounded-xl">
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            返回控制台
                        </Button>
                    </Link>
                }
            />

            <div className="grid gap-6 xl:grid-cols-[260px_minmax(0,1fr)] xl:items-start">
                <aside className="xl:sticky xl:top-24">
                    <div className="rounded-[1.5rem] border border-border/60 bg-card/90 p-4 shadow-sm backdrop-blur-sm">
                        <h2 className="mb-3 text-sm font-semibold text-foreground">设置分组</h2>

                        <nav className="space-y-2" aria-label="设置分组导航">
                            {SETTINGS_TABS.map((tab) => {
                                const Icon = tab.icon;
                                const isActive = currentTab.id === tab.id;

                                return (
                                    <Link
                                        key={tab.id}
                                        href={tab.href}
                                        aria-current={isActive ? "page" : undefined}
                                        className={cn(
                                            "flex items-start gap-3 rounded-[1.25rem] border px-4 py-3 text-sm transition-all duration-200",
                                            isActive
                                                ? "border-primary/25 bg-primary/8 text-foreground shadow-sm"
                                                : "border-border/70 bg-background/60 text-muted-foreground hover:border-primary/15 hover:text-foreground",
                                        )}
                                    >
                                        <div className={cn("rounded-xl bg-muted p-2", isActive && "bg-background", isActive && tab.color)}>
                                            <Icon className="h-4 w-4" />
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            <p className="font-medium">{tab.label}</p>
                                            <p className="mt-1 text-xs leading-5 text-muted-foreground">{tab.desc}</p>
                                        </div>
                                    </Link>
                                );
                            })}
                        </nav>
                    </div>
                </aside>

                <div className="min-w-0 rounded-[1.75rem] border border-border/60 bg-background/35 p-1.5">
                    <div className="min-w-0 rounded-[1.5rem] bg-transparent p-2 sm:p-3">{children}</div>
                </div>
            </div>
        </div>
    );
}
