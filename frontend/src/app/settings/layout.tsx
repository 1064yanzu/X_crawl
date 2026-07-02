"use client";
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
};

const SETTINGS_TABS: SettingsTab[] = [
    { id: "general", label: "通用设置", href: "/settings", icon: Wrench, desc: "浏览器、引擎参数、代理与归档" },
    { id: "x", label: "𝕏 Twitter", href: "/settings/x", icon: Twitter, desc: "X 平台 Cookie 与账号池管理" },
    { id: "weibo", label: "微博", href: "/settings/weibo", icon: Globe, desc: "微博凭证与平台专属配置" },
    { id: "youtube", label: "YouTube", href: "/settings/youtube", icon: Youtube, desc: "YouTube API Key 池与配额监控" },
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
        <div className="space-y-12 pb-16 editorial-rise">
            <PageHeader
                eyebrow="第 01 期 · 设置"
                icon={Settings}
                title="系统设置"
                description="管理系统与平台配置。"
                actions={
                    <Link href="/">
                        <Button variant="outline">
                            <ArrowLeft className="mr-2 h-3.5 w-3.5" />
                            返回控制台
                        </Button>
                    </Link>
                }
            />

            <div className="grid gap-12 xl:grid-cols-[240px_minmax(0,1fr)] xl:items-start">
                <aside className="xl:sticky xl:top-24">
                    <p className="px-1 pb-4 font-mono text-[10px] uppercase tracking-[0.26em] text-[color:var(--fg-subtle)]">
                        Chapters
                    </p>
                    <nav aria-label="设置分组导航">
                        <ol className="flex flex-col gap-px">
                            {SETTINGS_TABS.map((tab, idx) => {
                                const isActive = currentTab.id === tab.id;
                                return (
                                    <li key={tab.id}>
                                        <Link
                                            href={tab.href}
                                            aria-current={isActive ? "page" : undefined}
                                            className={cn(
                                                "group relative flex items-baseline gap-3 px-2 py-3 transition-colors duration-200",
                                                isActive
                                                    ? "text-foreground"
                                                    : "text-[color:var(--fg-muted)] hover:text-foreground",
                                            )}
                                        >
                                            <span
                                                aria-hidden
                                                className={cn(
                                                    "block h-[1.5px] transition-all duration-300 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
                                                    isActive
                                                        ? "w-6 bg-[var(--accent)]"
                                                        : "w-2 bg-[color:var(--line-strong)] group-hover:w-5 group-hover:bg-[var(--accent)]",
                                                )}
                                            />
                                            <div className="flex-1">
                                                <div className="flex items-baseline gap-2">
                                                    <span className="font-mono text-[10px] tracking-[0.22em] text-[color:var(--fg-subtle)]">
                                                        {String(idx + 1).padStart(2, "0")}
                                                    </span>
                                                    <span className="font-serif text-[15px] tracking-tight">{tab.label}</span>
                                                </div>
                                                <p className="mt-1 text-[12px] leading-5 text-[color:var(--fg-subtle)]">{tab.desc}</p>
                                            </div>
                                        </Link>
                                    </li>
                                );
                            })}
                        </ol>
                    </nav>
                </aside>

                <div className="min-w-0">{children}</div>
            </div>
        </div>
    );
}
