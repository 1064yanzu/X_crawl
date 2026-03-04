"use client";

import { Twitter, Users } from "lucide-react";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { CookieManager } from "@/components/features/CookieManager";
import { AccountPoolCard } from "@/components/features/AccountPoolCard";

export default function XSettingsPage() {
    return (
        <div className="grid gap-6 animate-in fade-in duration-300">
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Twitter className="h-5 w-5 text-blue-500" /> X/Twitter Cookie
                        管理
                    </CardTitle>
                    <CardDescription>
                        管理 X/Twitter 登录 Cookie，抓取时自动注入。
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <CookieManager />
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Users className="h-5 w-5 text-violet-500" /> X 多账号池
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
        </div>
    );
}
