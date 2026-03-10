import type { LucideIcon } from "lucide-react";
import { Bookmark, Database, Settings, Terminal } from "lucide-react";

export type NavItem = {
    name: string;
    href: string;
    hint: string;
    icon: LucideIcon;
};

export const NAV_ITEMS: NavItem[] = [
    { name: "控制台", href: "/", icon: Terminal, hint: "创建与总览" },
    { name: "采集任务", href: "/tasks", icon: Database, hint: "查看运行状态" },
    { name: "断点续传", href: "/checkpoints", icon: Bookmark, hint: "恢复中断任务" },
    { name: "设置", href: "/settings", icon: Settings, hint: "浏览器与账号" },
];

export function isActivePath(pathname: string, href: string) {
    return pathname === href || (href !== "/" && pathname.startsWith(href));
}

export function getCurrentNav(pathname: string) {
    return NAV_ITEMS.find((item) => isActivePath(pathname, item.href)) ?? NAV_ITEMS[0];
}
