"use client";
import * as React from "react";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";

const STORAGE_KEY = "xcrawl-theme";

type ThemeMode = "light" | "dark";

function applyTheme(mode: ThemeMode) {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.theme = mode;
}

export function ThemeToggle() {
    const [mounted, setMounted] = React.useState(false);
    const [theme, setTheme] = React.useState<ThemeMode>("light");

    React.useEffect(() => {
        const stored = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
        const systemDark = typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
        const nextTheme: ThemeMode = stored === "dark" || stored === "light" ? stored : systemDark ? "dark" : "light";
        setTheme(nextTheme);
        applyTheme(nextTheme);
        setMounted(true);
    }, []);

    const toggle = () => {
        const nextTheme: ThemeMode = theme === "dark" ? "light" : "dark";
        setTheme(nextTheme);
        if (typeof window !== "undefined") {
            window.localStorage.setItem(STORAGE_KEY, nextTheme);
        }
        applyTheme(nextTheme);
    };

    if (!mounted) {
        return <div className="h-9 w-9 rounded-xl border border-border/60 bg-card/80" aria-hidden="true" />;
    }

    return (
        <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={toggle}
            className="rounded-xl border border-border/60 bg-card/80 text-muted-foreground hover:text-foreground"
            aria-label={theme === "dark" ? "切换到浅色模式" : "切换到深色模式"}
            title={theme === "dark" ? "切换到浅色模式" : "切换到深色模式"}
        >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
    );
}
