"use client";
import Image from "next/image";
import { AlertCircle, ShieldAlert } from "lucide-react";
import { API_BASE_URL } from "@/services/api";
import { getRiskStateHint, getRiskStateLabel } from "@/lib/task-ui";

type Props = {
    error?: string | null;
    isRiskPaused: boolean;
    riskState?: string | null;
    debugScreenshot?: string | null;
};

export function TaskAlerts({ error, isRiskPaused, riskState, debugScreenshot }: Props) {
    const riskLabel = getRiskStateLabel(riskState);
    const riskHint = getRiskStateHint(riskState);
    return (
        <div className="space-y-3">
            {error ? (
                <div className="rounded-md border border-red-200 bg-red-50/90 p-4 text-red-800 shadow-sm dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200">
                    <div className="flex items-start gap-3">
                        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                        <div className="min-w-0 flex-1">
                            <p className="font-semibold">任务执行中断</p>
                            <p className="mt-1 text-sm leading-6 text-red-700/90 dark:text-red-200/90">
                                后端已返回错误信息。你可以先查看下方动作流和结果，再决定是否继续爬取。
                            </p>
                            <pre className="mt-3 overflow-x-auto rounded-md border border-red-200/80 bg-white/70 px-3 py-3 text-xs text-red-900 dark:border-red-500/10 dark:bg-black/20 dark:text-red-100">{error}</pre>
                        </div>
                    </div>

                    {debugScreenshot ? (
                        <details className="mt-4 rounded-md border border-red-200/80 bg-white/60 p-3 dark:border-red-500/10 dark:bg-black/10">
                            <summary className="cursor-pointer text-sm font-medium">查看错误截图</summary>
                            <div className="mt-3 space-y-3">
                                <a href={API_BASE_URL + debugScreenshot} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">
                                    在新窗口打开原图
                                </a>
                                <Image
                                    src={API_BASE_URL + debugScreenshot}
                                    alt="Debug Screenshot"
                                    width={1600}
                                    height={900}
                                    className="h-auto max-h-[600px] w-full rounded-md border border-red-200 bg-white object-contain dark:border-red-500/10 dark:bg-black"
                                    unoptimized
                                />
                            </div>
                        </details>
                    ) : null}
                </div>
            ) : null}

            {isRiskPaused ? (
                <div className="rounded-md border border-orange-200 bg-orange-50/90 p-4 text-orange-900 shadow-sm dark:border-orange-500/20 dark:bg-orange-500/10 dark:text-orange-100">
                    <div className="flex items-start gap-3">
                        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
                        <div>
                            <p className="font-semibold">检测到风险状态：{riskLabel}</p>
                            <p className="mt-1 text-sm leading-6 text-orange-800/90 dark:text-orange-100/90">
                                {riskHint}
                            </p>
                        </div>
                    </div>
                </div>
            ) : null}
        </div>
    );
}
