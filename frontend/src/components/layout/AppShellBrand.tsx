import Link from "next/link";
import { Activity } from "lucide-react";

export function AppShellBrand() {
    return (
        <Link href="/" className="group flex min-w-0 items-center gap-3">
            <div className="rounded-2xl border border-border/70 bg-background p-2.5 shadow-sm transition-transform group-hover:scale-[1.03]">
                <Activity className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0">
                <p className="text-sm font-semibold tracking-wide text-foreground">X_crawler</p>
                <p className="text-xs text-muted-foreground">多平台采集控制台</p>
            </div>
        </Link>
    );
}
