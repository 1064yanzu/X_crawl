"use client";
import { Monitor, Shield } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BrowserSelector } from "@/components/features/BrowserSelector";
import { CrawlerConfigCard } from "@/components/features/settings/CrawlerConfigCard";
import { EngineConfigCard } from "@/components/features/settings/EngineConfigCard";
import { ProxyConfigCard } from "@/components/features/settings/ProxyConfigCard";
import { RawResponseStorageCard } from "@/components/features/settings/RawResponseStorageCard";

export default function GeneralSettingsPage() {
    return (
        <div className="grid gap-6 animate-in fade-in duration-300">
            <Card className="rounded-lg border-border bg-card ">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-xl">
                        <Monitor className="h-5 w-5 text-indigo-500" /> 浏览器选择
                    </CardTitle>
                    <CardDescription>
                        先确定爬虫使用哪个浏览器实例。这个设置影响所有任务，是最值得优先确认的一项。
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <BrowserSelector />
                </CardContent>
            </Card>

            <CrawlerConfigCard />
            <EngineConfigCard />
            <ProxyConfigCard />
            <RawResponseStorageCard />

            <Card className="rounded-lg border-red-200/70 bg-red-50/70 dark:border-red-500/20 dark:bg-red-500/10">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-xl">
                        <Shield className="h-5 w-5" /> 高风险操作
                    </CardTitle>
                    <CardDescription>仅放破坏性操作，避免和普通配置混在一起。</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-col gap-4 rounded-md border border-red-200/80 bg-white/70 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-red-500/10 dark:bg-black/10">
                        <div>
                            <h4 className="font-medium text-red-700 dark:text-red-200">清理浏览器缓存</h4>
                            <p className="mt-1 text-sm leading-6 text-red-700/80 dark:text-red-200/80">
                                会清理本地浏览器用户数据目录（不含 Cookie 文件），建议只在排查异常时使用。
                            </p>
                        </div>
                        <Button variant="destructive" size="sm" disabled>
                            即将开放
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
