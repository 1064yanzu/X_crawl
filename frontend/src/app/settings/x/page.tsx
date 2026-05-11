"use client";
import { Twitter, Users } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CookieManager } from "@/components/features/CookieManager";
import { AccountPoolCard } from "@/components/features/AccountPoolCard";

export default function XSettingsPage() {
    return (
        <div className="grid gap-6 animate-in fade-in duration-300">
            <Card className="rounded-lg border-border bg-card ">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-xl">
                        <Twitter className="h-5 w-5 text-blue-500" /> X / Twitter Cookie 管理
                    </CardTitle>
                    <CardDescription>
                        先确保登录凭证可用，再继续维护账号池；这能明显降低任务失败和频繁登录的概率。
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <CookieManager />
                </CardContent>
            </Card>

            <Card className="rounded-lg border-border bg-card ">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-xl">
                        <Users className="h-5 w-5 text-violet-500" /> X 多账号池
                    </CardTitle>
                    <CardDescription>
                        保存 Cookie 后账号会自动同步到这里。多账号能分摊速率限制，提高长时间运行任务的稳定性。
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <AccountPoolCard />
                </CardContent>
            </Card>
        </div>
    );
}
