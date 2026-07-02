"use client";

import * as React from "react";
import { ArrowDownToLine, FileText, Info, Loader2, RefreshCw } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { api, SystemAbout } from "@/services/api";

export function AboutCard() {
    const { push } = useToast();
    const [about, setAbout] = React.useState<SystemAbout | null>(null);
    const [loading, setLoading] = React.useState(true);
    const [diagnosing, setDiagnosing] = React.useState(false);

    const refresh = React.useCallback(async () => {
        setLoading(true);
        try {
            setAbout(await api.system.getAbout());
        } catch (err) {
            push({
                type: "error",
                title: "加载关于信息失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setLoading(false);
        }
    }, [push]);

    React.useEffect(() => {
        void refresh();
    }, [refresh]);

    const handleDiagnose = async () => {
        setDiagnosing(true);
        try {
            const result = await api.system.diagnose();
            push({
                type: "success",
                title: "诊断包已生成",
                description: `${result.filename} · ${formatBytes(result.size_bytes)}（位于数据目录）`,
            });
        } catch (err) {
            push({
                type: "error",
                title: "诊断失败",
                description: err instanceof Error ? err.message : String(err),
            });
        } finally {
            setDiagnosing(false);
        }
    };

    return (
        <Card className="rounded-lg border-border bg-card ">
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                    <Info className="h-5 w-5 text-slate-500" /> 关于 · 诊断
                </CardTitle>
                <CardDescription>
                    版本信息、关键路径、schema 迁移历史。导出诊断包后可以把 zip 文件附在反馈里方便定位问题。
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
                {loading || !about ? (
                    <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在读取关于信息...
                    </div>
                ) : (
                    <>
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                            <Meta label="后端版本" value={about.version} />
                            <Meta label="Python" value={about.python} />
                            <Meta label="平台" value={about.platform} />
                            <Meta label="模式" value={about.dev_mode ? "开发模式（docs 开启）" : "生产模式（docs 关闭）"} />
                            <Meta label="Schema 当前版本" value={String(about.migrations?.current_version ?? "?")} />
                            <Meta label="Schema 最新版本" value={String(about.migrations?.latest_version ?? "?")} />
                        </div>

                        <div className="rounded-md border border-border bg-muted/20 p-4 shadow-sm">
                            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">关键路径</p>
                            <ul className="mt-2 space-y-1 text-xs leading-relaxed text-foreground">
                                <PathRow label="data" value={about.data_dir} />
                                <PathRow label="tasks_db" value={about.tasks_db} />
                                <PathRow label="raw_responses" value={about.raw_responses_dir} />
                                <PathRow label="logs" value={about.log_dir} />
                            </ul>
                        </div>

                        {about.migrations?.registered && about.migrations.registered.length > 0 ? (
                            <div className="rounded-md border border-border bg-background p-4 shadow-sm">
                                <p className="flex items-center gap-1.5 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                                    <FileText className="h-3.5 w-3.5" /> 迁移历史
                                </p>
                                <ul className="mt-2 space-y-1 text-xs">
                                    {about.migrations.registered.map((m) => (
                                        <li key={m.version} className="flex items-center gap-3">
                                            <span className="font-mono text-muted-foreground">v{m.version}</span>
                                            <span>{m.description}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        ) : null}

                        <div className="flex flex-wrap items-center gap-2">
                            <Button variant="outline" size="sm" className="rounded-md" onClick={refresh}>
                                <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> 刷新
                            </Button>
                            <Button size="sm" className="rounded-md" onClick={handleDiagnose} disabled={diagnosing}>
                                {diagnosing ? (
                                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                                ) : (
                                    <ArrowDownToLine className="mr-1.5 h-3.5 w-3.5" />
                                )}
                                导出诊断包
                            </Button>
                        </div>
                    </>
                )}
            </CardContent>
        </Card>
    );
}

function Meta({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-md border border-border bg-muted/20 p-3 shadow-sm">
            <p className="text-[10.5px] uppercase tracking-[0.22em] text-muted-foreground">{label}</p>
            <p className="mt-1 text-xs text-foreground">{value}</p>
        </div>
    );
}

function PathRow({ label, value }: { label: string; value: string }) {
    return (
        <li className="flex items-baseline gap-3">
            <span className="w-24 shrink-0 font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
                {label}
            </span>
            <span className="break-all font-mono text-[11.5px] text-foreground">{value}</span>
        </li>
    );
}

function formatBytes(n: number): string {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
}
