"use client";

import * as React from "react";
import { AppWindow, Bell, Loader2, Maximize2, Save } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

interface DesktopPreferences {
    notifyOnTaskDone: boolean;
    confirmOnQuit: "always" | "if-active" | "never";
    rememberWindowState: boolean;
}

interface XCrawlBridge {
    isDesktop: boolean;
    getPreferences: () => Promise<DesktopPreferences>;
    setPreferences: (patch: Partial<DesktopPreferences>) => Promise<DesktopPreferences>;
    resetWindow: () => Promise<boolean>;
    openLogDir: () => Promise<boolean>;
    openDataDir: () => Promise<boolean>;
    getRuntimeInfo: () => Promise<{
        version: string;
        platform: string;
        dataDir: string;
        logDir: string;
        backendPort: number | null;
    }>;
}

function getBridge(): XCrawlBridge | null {
    if (typeof window === "undefined") return null;
    const w = window as unknown as { xcrawl?: XCrawlBridge };
    return w.xcrawl ?? null;
}

export function DesktopCard() {
    const [bridge] = React.useState<XCrawlBridge | null>(() => getBridge());
    const [prefs, setPrefs] = React.useState<DesktopPreferences | null>(null);
    const [draft, setDraft] = React.useState<DesktopPreferences | null>(null);
    const [info, setInfo] = React.useState<{ version: string; platform: string; dataDir: string; logDir: string } | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);
    const { push } = useToast();

    React.useEffect(() => {
        if (!bridge) {
            setLoading(false);
            return;
        }
        (async () => {
            try {
                const [p, rt] = await Promise.all([
                    bridge.getPreferences(),
                    bridge.getRuntimeInfo(),
                ]);
                setPrefs(p);
                setDraft(p);
                setInfo({
                    version: rt.version,
                    platform: rt.platform,
                    dataDir: rt.dataDir,
                    logDir: rt.logDir,
                });
            } finally {
                setLoading(false);
            }
        })();
    }, [bridge]);

    if (!bridge) return null;  // 仅 Electron 显示

    const dirty = prefs && draft &&
        (prefs.notifyOnTaskDone !== draft.notifyOnTaskDone ||
            prefs.confirmOnQuit !== draft.confirmOnQuit ||
            prefs.rememberWindowState !== draft.rememberWindowState);

    const handleSave = async () => {
        if (!draft) return;
        setSaving(true);
        try {
            const updated = await bridge.setPreferences(draft);
            setPrefs(updated);
            setDraft(updated);
            push({ type: "success", title: "桌面端偏好已保存" });
        } catch (err) {
            push({
                type: "error",
                title: "保存失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Card className="rounded-lg border-border bg-card ">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                    <AppWindow className="h-5 w-5 text-cyan-500" /> 桌面端体验
                </CardTitle>
                <CardDescription>
                    只在桌面壳里出现的偏好。改这里不会影响爬虫行为，只影响窗口、通知和退出方式。
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
                {loading || !draft ? (
                    <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在读取桌面端偏好...
                    </div>
                ) : (
                    <>
                        <ToggleRow
                            icon={Bell}
                            label="任务完成系统通知"
                            description="任务进入 done / stopped / failed 时弹出系统通知。点击通知会聚焦主窗口。"
                            checked={draft.notifyOnTaskDone}
                            onChange={(v) => setDraft({ ...draft, notifyOnTaskDone: v })}
                        />

                        <div className="rounded-md border border-border bg-background p-4 shadow-sm">
                            <p className="text-sm font-medium text-foreground">退出前确认</p>
                            <p className="mt-1 text-xs leading-5 text-muted-foreground">
                                防止误关导致任务被强制打断。任务即使被打断也会在断点续爬，但确认一下更稳。
                            </p>
                            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
                                {(["always", "if-active", "never"] as const).map((mode) => (
                                    <button
                                        key={mode}
                                        type="button"
                                        onClick={() => setDraft({ ...draft, confirmOnQuit: mode })}
                                        className={`rounded-md border px-3 py-2 text-left text-xs transition-colors ${
                                            draft.confirmOnQuit === mode
                                                ? "border-primary bg-primary/10 text-foreground"
                                                : "border-border bg-background text-muted-foreground hover:border-primary/50"
                                        }`}
                                    >
                                        <p className="font-medium">
                                            {mode === "always" ? "每次都问" : mode === "if-active" ? "仅有活跃任务时" : "从不询问"}
                                        </p>
                                        <p className="mt-0.5 text-[10.5px] leading-4 text-muted-foreground">
                                            {mode === "always"
                                                ? "无论有没有任务，关窗都弹"
                                                : mode === "if-active"
                                                  ? "推荐。安静时直接退出"
                                                  : "永远不弹，点关就走"}
                                        </p>
                                    </button>
                                ))}
                            </div>
                        </div>

                        <ToggleRow
                            icon={Maximize2}
                            label="记住窗口位置与大小"
                            description="下次启动还原上次关闭时的位置。关闭后总是用默认 1440×900 居中显示。"
                            checked={draft.rememberWindowState}
                            onChange={(v) => setDraft({ ...draft, rememberWindowState: v })}
                        />

                        <div className="flex flex-col gap-3 rounded-lg border border-border bg-background p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                            <div className="flex flex-wrap items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="rounded-md"
                                    onClick={async () => {
                                        await bridge.resetWindow();
                                        push({ type: "success", title: "已重置主窗口尺寸" });
                                    }}
                                >
                                    重置窗口大小
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="rounded-md"
                                    onClick={() => void bridge.openLogDir()}
                                >
                                    打开日志目录
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="rounded-md"
                                    onClick={() => void bridge.openDataDir()}
                                >
                                    打开数据目录
                                </Button>
                            </div>
                            <Button
                                size="sm"
                                className="rounded-md"
                                onClick={handleSave}
                                disabled={saving || !dirty}
                            >
                                {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
                                保存
                            </Button>
                        </div>

                        {info ? (
                            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                                <Meta label="桌面版本" value={info.version || "--"} />
                                <Meta label="平台" value={(info.platform || "?").toUpperCase()} />
                                <Meta label="数据目录" value={info.dataDir} mono break />
                                <Meta label="日志目录" value={info.logDir} mono break />
                            </div>
                        ) : null}
                    </>
                )}
            </CardContent>
        </Card>
    );
}

function ToggleRow({
    icon: Icon,
    label,
    description,
    checked,
    onChange,
}: {
    icon: React.ElementType;
    label: string;
    description: string;
    checked: boolean;
    onChange: (v: boolean) => void;
}) {
    return (
        <label className="flex items-start justify-between gap-3 rounded-md border border-border bg-background p-4 shadow-sm">
            <div className="flex flex-1 items-start gap-3">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div>
                    <p className="text-sm font-medium text-foreground">{label}</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
                </div>
            </div>
            <span className="relative mt-0.5 inline-flex cursor-pointer items-center">
                <input
                    type="checkbox"
                    className="peer sr-only"
                    checked={checked}
                    onChange={(e) => onChange(e.target.checked)}
                />
                <span className="h-6 w-11 rounded-full bg-muted transition-colors peer-checked:bg-primary" />
                <span className="absolute left-[2px] top-[2px] h-5 w-5 rounded-full border bg-white transition-transform peer-checked:translate-x-full" />
            </span>
        </label>
    );
}

function Meta({ label, value, mono, break: brk }: { label: string; value: string; mono?: boolean; break?: boolean }) {
    return (
        <div className="rounded-md border border-border bg-muted/20 p-3 shadow-sm">
            <p className="text-[10.5px] uppercase tracking-[0.22em] text-muted-foreground">{label}</p>
            <p className={`mt-1 text-xs text-foreground ${mono ? "font-mono" : ""} ${brk ? "break-all" : ""}`}>{value}</p>
        </div>
    );
}
