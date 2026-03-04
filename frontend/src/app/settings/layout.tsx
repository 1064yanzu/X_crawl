"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, Globe, Settings, Twitter, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type SettingsTab = {
    id: string;
    label: string;
    href: string;
    icon: React.ElementType;
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
        desc: "X 平台 Cookie 与账号管理",
        color: "text-blue-600 dark:text-blue-400",
    },
    {
        id: "weibo",
        label: "微博",
        href: "/settings/weibo",
        icon: Globe,
        desc: "微博平台 Cookie 管理",
        color: "text-orange-500 dark:text-orange-400",
    },
];

function getActiveTab(pathname: string): SettingsTab {
    if (pathname === "/settings/x") return SETTINGS_TABS[1];
    if (pathname === "/settings/weibo") return SETTINGS_TABS[2];
    return SETTINGS_TABS[0];
}

export default function SettingsLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const pathname = usePathname();
    const currentTab = getActiveTab(pathname);

    return (
        <div className="mx-auto max-w-4xl space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
                        <Settings className="h-7 w-7 text-primary" /> 系统设置
                    </h1>
                    <p className="mt-2 text-muted-foreground">
                        管理爬虫内核参数、Cookie 凭证、网络代理与归档偏好设置。
                    </p>
                </div>
                <Link href="/">
                    <Button
                        variant="ghost"
                        className="gap-1.5 text-muted-foreground hover:text-foreground"
                    >
                        <ArrowLeft className="h-4 w-4" /> 返回主页
                    </Button>
                </Link>
            </div>

            {/* 设置分类 Tab */}
            <div className="inline-flex items-center gap-1 p-1 bg-muted/50 rounded-xl border border-border/30 w-full sm:w-auto overflow-x-auto">
                {SETTINGS_TABS.map((tab) => {
                    const Icon = tab.icon;
                    const isActive = currentTab.id === tab.id;
                    return (
                        <Link
                            key={tab.id}
                            href={tab.href}
                            className={cn(
                                "flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer whitespace-nowrap flex-1 sm:flex-initial justify-center",
                                isActive
                                    ? "bg-background text-foreground shadow-sm border border-border/60"
                                    : "text-muted-foreground hover:text-foreground hover:bg-background/60"
                            )}
                        >
                            <Icon
                                className={cn("w-4 h-4 shrink-0", isActive && tab.color)}
                            />
                            <span>{tab.label}</span>
                        </Link>
                    );
                })}
            </div>

            {/* Tab 描述 */}
            <p className="text-sm text-muted-foreground -mt-4">{currentTab.desc}</p>

            {/* 子页面内容 */}
            {children}

            <div className="pb-8" />
        </div>
    );
}
