"use client";
import { Globe } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { WeiboCookieManager } from "@/components/features/WeiboCookieManager";

export default function WeiboSettingsPage() {
    return (
        <div className="grid gap-6 animate-in fade-in duration-300">
            <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-xl">
                        <Globe className="h-5 w-5 text-orange-500" /> 微博 Cookie 管理
                    </CardTitle>
                    <CardDescription>
                        在这里维护微博平台的登录凭证与可用性。建议先验证登录状态，再启动批量回采任务。
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <WeiboCookieManager />
                </CardContent>
            </Card>
        </div>
    );
}
