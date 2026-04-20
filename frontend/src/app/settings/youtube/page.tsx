"use client";
import { Info, Youtube } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { YouTubeApiKeyManager } from "@/components/features/YouTubeApiKeyManager";
import { YouTubeQuotaCard } from "@/components/features/YouTubeQuotaCard";

export default function YouTubeSettingsPage() {
    return (
        <div className="grid gap-6 animate-in fade-in duration-300">
            <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-xl">
                        <Youtube className="h-5 w-5 text-red-600 dark:text-red-400" /> YouTube 接入说明
                    </CardTitle>
                    <CardDescription className="space-y-2">
                        <p>
                            YouTube 采集使用 Google 官方 Data API v3，需要在 Google Cloud Console 创建 API Key。官方每个 Key 默认每日 10,000 单位配额（PT 00:00 重置）。
                        </p>
                        <p>
                            搜索（search.list）每次消耗 100 单位，视频/评论列表类调用 1 单位。支持多 Key 轮询，系统会根据剩余配额自动选择可用 Key。
                        </p>
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex items-start gap-3 rounded-2xl border border-red-200/70 bg-red-50/60 p-4 text-sm text-red-800 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-100">
                        <Info className="mt-0.5 h-4 w-4 shrink-0" />
                        <div className="space-y-1">
                            <p>
                                获取 Key：
                                <a
                                    className="ml-1 underline underline-offset-4"
                                    href="https://console.cloud.google.com/apis/library/youtube.googleapis.com"
                                    target="_blank"
                                    rel="noreferrer"
                                >
                                    Google Cloud → 启用 YouTube Data API v3
                                </a>
                                ，再到「凭据」页新建 API Key。
                            </p>
                            <p>
                                添加 Key 后建议立即点击「验证」，确认 Key 未被限制。若需要突破单 Key 配额上限，在本页追加多个 Key 即可。
                            </p>
                        </div>
                    </div>
                </CardContent>
            </Card>

            <YouTubeQuotaCard />

            <YouTubeApiKeyManager />
        </div>
    );
}
