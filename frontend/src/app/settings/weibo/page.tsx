"use client";

import { Globe } from "lucide-react";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { WeiboCookieManager } from "@/components/features/WeiboCookieManager";

export default function WeiboSettingsPage() {
    return (
        <div className="grid gap-6 animate-in fade-in duration-300">
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Globe className="h-5 w-5 text-orange-500" /> 微博 Cookie 管理
                    </CardTitle>
                    <CardDescription>
                        管理微博登录 Cookie，微博平台爬取时自动注入。
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <WeiboCookieManager />
                </CardContent>
            </Card>
        </div>
    );
}
