"use client";
import { AlertCircle, ShieldAlert } from "lucide-react";
import { API_BASE_URL } from "@/services/api";

type Props = {
    error?: string | null;
    isRiskPaused: boolean;
    debugScreenshot?: string | null;
};

export function TaskAlerts({ error, isRiskPaused, debugScreenshot }: Props) {
    return (
        <>
            {error && (
                <div className="bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 p-4 rounded-xl border border-red-200 dark:border-red-900/50 flex flex-col gap-3 shadow-sm">
                    <div className="flex gap-3">
                        <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                        <div>
                            <p className="font-bold">后台爬虫异常中断</p>
                            <p className="text-sm mt-1 font-mono bg-white/50 dark:bg-black/20 px-2 py-1 rounded mt-2">{error}</p>
                        </div>
                    </div>
                    {debugScreenshot && (
                        <div className="mt-2 border-t border-red-200 dark:border-red-900/50 pt-3">
                            <p className="font-bold mb-2 flex items-center gap-2">
                                📸 错误现场抓拍:
                                <a href={API_BASE_URL + debugScreenshot} target="_blank" rel="noreferrer" className="text-primary hover:underline text-xs font-normal">
                                    [点击放大查看]
                                </a>
                            </p>
                            <img src={API_BASE_URL + debugScreenshot} alt="Debug Screenshot" className="max-w-2xl w-full h-auto rounded border border-red-200 dark:border-red-900/50 object-contain max-h-[600px] bg-white dark:bg-black" />
                        </div>
                    )}
                </div>
            )}

            {isRiskPaused && (
                <div className="bg-orange-50 dark:bg-orange-950/20 text-orange-700 dark:text-orange-400 p-4 rounded-xl border border-orange-200 dark:border-orange-900/50 flex gap-3 shadow-sm">
                    <ShieldAlert className="w-5 h-5 shrink-0 mt-0.5" />
                    <div>
                        <p className="font-bold">检测到风控挑战，任务已自动暂停</p>
                        <p className="text-sm mt-1">请在浏览器完成验证后，点击右上角「继续」恢复采集。</p>
                    </div>
                </div>
            )}
        </>
    );
}

