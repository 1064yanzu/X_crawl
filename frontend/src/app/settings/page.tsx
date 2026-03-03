"use client";
import Link from "next/link";
import { ArrowLeft, Cookie, Monitor, Settings, Shield, Users } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CookieManager } from "@/components/features/CookieManager";
import { BrowserSelector } from "@/components/features/BrowserSelector";
import { CrawlerConfigCard } from "@/components/features/settings/CrawlerConfigCard";
import { EngineConfigCard } from "@/components/features/settings/EngineConfigCard";
import { ProxyConfigCard } from "@/components/features/settings/ProxyConfigCard";
import { RawResponseStorageCard } from "@/components/features/settings/RawResponseStorageCard";
import { AccountPoolCard } from "@/components/features/AccountPoolCard";

export default function SettingsPage() {
    return (
        <div className="mx-auto max-w-4xl space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
                        <Settings className="h-7 w-7 text-primary" /> 系统设置
                    </h1>
                    <p className="mt-2 text-muted-foreground">管理爬虫内核参数、Cookie 凭证、网络代理与归档偏好设置。</p>
                </div>
                <Link href="/">
                    <Button variant="ghost" className="gap-1.5 text-muted-foreground hover:text-foreground">
                        <ArrowLeft className="h-4 w-4" /> 返回主页
                    </Button>
                </Link>
            </div>

            <div className="grid gap-6">
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2"><Monitor className="h-5 w-5 text-indigo-500" /> 浏览器选择</CardTitle>
                        <CardDescription>选择爬虫使用的浏览器实例。仅 Chromium 内核浏览器可用于爬取。</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <BrowserSelector />
                    </CardContent>
                </Card>

                <CrawlerConfigCard />
                <EngineConfigCard />

                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2"><Cookie className="h-5 w-5 text-amber-600" /> Cookie 管理</CardTitle>
                        <CardDescription>管理 X/Twitter 登录 Cookie，抓取时自动注入。</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <CookieManager />
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Users className="h-5 w-5 text-violet-500" /> 多账号池
                        </CardTitle>
                        <CardDescription>
                            保存 Cookie 后账号自动同步到此处。N 个账号可将速率限制分摊，
                            将搜索间隔从 ~18s 缩短至 ~18s/N，大幅提升爬取效率。
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <AccountPoolCard />
                    </CardContent>
                </Card>

                <ProxyConfigCard />
                <RawResponseStorageCard />

                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2"><Shield className="h-5 w-5" /> 安全操作</CardTitle>
                        <CardDescription>高风险操作区域，请谨慎使用。</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center justify-between rounded-lg border border-red-500/20 bg-red-500/10 p-4">
                            <div>
                                <h4 className="font-medium text-red-600 dark:text-red-400">清理浏览器缓存</h4>
                                <p className="mt-1 text-sm text-red-600/80 dark:text-red-400/80">该功能会清理本地浏览器用户数据目录（不含 Cookie 文件）。</p>
                            </div>
                            <Button variant="destructive" size="sm" disabled>
                                即将开放
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            </div>
            <div className="pb-8" />
        </div>
    );
}
