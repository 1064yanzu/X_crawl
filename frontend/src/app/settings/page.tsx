"use client";

import { Monitor, Shield } from "lucide-react";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BrowserSelector } from "@/components/features/BrowserSelector";
import { CrawlerConfigCard } from "@/components/features/settings/CrawlerConfigCard";
import { EngineConfigCard } from "@/components/features/settings/EngineConfigCard";
import { ProxyConfigCard } from "@/components/features/settings/ProxyConfigCard";
import { RawResponseStorageCard } from "@/components/features/settings/RawResponseStorageCard";

export default function GeneralSettingsPage() {
    return (
        <div className="grid gap-6 animate-in fade-in duration-300">
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Monitor className="h-5 w-5 text-indigo-500" /> 浏览器选择
                    </CardTitle>
                    <CardDescription>
                        选择爬虫使用的浏览器实例。仅 Chromium 内核浏览器可用于爬取。
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

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Shield className="h-5 w-5" /> 安全操作
                    </CardTitle>
                    <CardDescription>高风险操作区域，请谨慎使用。</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center justify-between rounded-lg border border-red-500/20 bg-red-500/10 p-4">
                        <div>
                            <h4 className="font-medium text-red-600 dark:text-red-400">
                                清理浏览器缓存
                            </h4>
                            <p className="mt-1 text-sm text-red-600/80 dark:text-red-400/80">
                                该功能会清理本地浏览器用户数据目录（不含 Cookie 文件）。
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
