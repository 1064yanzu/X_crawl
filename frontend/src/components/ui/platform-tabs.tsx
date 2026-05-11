"use client";

import * as React from "react";
import { Twitter, Globe, Bot, Rss, Youtube } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PlatformMeta } from "@/lib/platformRegistry";

/** 图标名称到 Lucide 组件的映射 */
const ICON_MAP: Record<string, React.ElementType> = {
    twitter: Twitter,
    globe: Globe,
    bot: Bot,
    rss: Rss,
    youtube: Youtube,
};

interface PlatformTabsProps {
    /** 要展示的平台列表（通常包含 "全部"） */
    platforms: PlatformMeta[];
    /** 当前选中的平台 ID */
    value: string;
    /** 切换回调 */
    onChange: (platformId: string) => void;
    /** 各平台计数（可选），key 为平台 id */
    counts?: Record<string, number>;
    /** 额外的 className */
    className?: string;
}

/**
 * 可复用的平台 Tab 切换器
 *
 * 分段控制器设计，每个 Tab 带图标 + 名称 + 可选计数
 */
export function PlatformTabs({
    platforms,
    value,
    onChange,
    counts,
    className,
}: PlatformTabsProps) {
    return (
        <div
            className={cn(
 "inline-flex items-center gap-1 p-1 bg-muted/50 rounded-md border border-border",
                className
            )}
        >
            {platforms.map((platform) => {
                const Icon = ICON_MAP[platform.iconName] ?? Bot;
                const isActive = value === platform.id;
                const count = counts?.[platform.id];

                return (
                    <button
                        key={platform.id}
                        type="button"
                        onClick={() => onChange(platform.id)}
                        className={cn(
 "flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer whitespace-nowrap",
                            isActive
                                ? "bg-background text-foreground shadow-sm border border-border"
                                : "text-muted-foreground hover:text-foreground hover:bg-background"
                        )}
                    >
                        <Icon className="w-3.5 h-3.5 shrink-0" />
                        <span>{platform.label}</span>
                        {typeof count === "number" && (
                            <span
                                className={cn(
 "inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold leading-none",
                                    isActive
                                        ? "bg-primary/10 text-primary"
                                        : "bg-muted text-muted-foreground"
                                )}
                            >
                                {count}
                            </span>
                        )}
                    </button>
                );
            })}
        </div>
    );
}
