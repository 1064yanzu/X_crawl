import Link from "next/link";
import { cn } from "@/lib/utils";
import { type NavItem, isActivePath } from "@/components/layout/app-shell-config";

/**
 * 编辑感主导航 — 杂志目录 (table of contents) 风格：
 * 极简文字列表，左侧细线锚定当前页，hover 时印刷红短线靠近。
 */
export function AppShellNavMenu({
    pathname,
    items,
    ariaLabel,
    mobile = false,
}: {
    pathname: string;
    items: NavItem[];
    ariaLabel: string;
    mobile?: boolean;
}) {
    return (
        <nav
            className={cn(
 "flex flex-col",
                mobile && "flex-1 overflow-y-auto px-3 py-4",
            )}
            aria-label={ariaLabel}
        >
            <p className="px-3 pb-3 font-mono text-[10px] uppercase tracking-[0.26em] text-[color:var(--fg-subtle)]">
                Sections
            </p>
            <ol className="flex flex-col gap-px">
                {items.map((item, idx) => {
                    const isActive = isActivePath(pathname, item.href);
                    return (
                        <li key={item.href}>
                            <Link
                                href={item.href}
                                aria-current={isActive ? "page" : undefined}
                                className={cn(
 "group relative flex items-baseline gap-3 px-3 py-2.5",
 "transition-colors duration-200 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]",
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
                                <span className="flex-1 truncate">
                                    <span className="font-mono text-[10px] tracking-[0.2em] text-[color:var(--fg-subtle)]">
                                        {String(idx + 1).padStart(2, "0")}
                                    </span>
                                    <span className="ml-2 font-serif text-[15px] tracking-tight">
                                        {item.name}
                                    </span>
                                </span>
                                {isActive ? (
                                    <span
                                        aria-hidden
                                        className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--accent)]"
                                    >
                                        Live
                                    </span>
                                ) : null}
                            </Link>
                        </li>
                    );
                })}
            </ol>
        </nav>
    );
}
