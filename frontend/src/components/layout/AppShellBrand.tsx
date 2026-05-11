import Link from "next/link";

/**
 * Brand — 刊头风格：
 * 顶部一行小字签 + 衬线大字 wordmark + 副标题
 */
export function AppShellBrand() {
    return (
        <Link href="/" className="group block min-w-0 select-none">
            <p className="font-mono text-[10px] uppercase tracking-[0.32em] text-[color:var(--fg-subtle)]">
                Multi-platform · Crawler
            </p>
            <p className="mt-1 font-serif text-[1.55rem] font-medium leading-none tracking-tight text-foreground transition-colors group-hover:text-[var(--accent)]">
                X_crawl
                <span
                    aria-hidden
                    className="ml-[2px] inline-block h-[10px] w-[3px] translate-y-[1px] bg-[var(--accent)]"
                />
            </p>
            <p className="mt-2 text-[12px] leading-5 text-[color:var(--fg-muted)]">
                多平台数据采集
            </p>
        </Link>
    );
}
