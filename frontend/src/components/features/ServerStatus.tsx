"use client";
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { AppWindow, ActivitySquare } from "lucide-react";
import { useHealthQuery } from "@/hooks/useHealth";

export function ServerStatus() {
    const { data: health, isLoading: loading, isError: error } = useHealthQuery();

    if (loading) {
        return <div className="animate-pulse h-12 bg-muted/50 rounded-lg w-full max-w-sm" />;
    }

    return (
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 bg-card/40 backdrop-blur-md border border-border/50 p-4 rounded-xl shadow-sm">
            <div className="flex items-center gap-3">
                <div className="p-2 bg-secondary rounded-full">
                    <ActivitySquare className="w-5 h-5 text-primary" />
                </div>
                <div>
                    <p className="text-sm font-medium leading-none mb-1">后端服务器</p>
                    <div className="flex items-center gap-2">
                        {error ? (
                            <Badge variant="destructive">离线</Badge>
                        ) : (
                            <Badge variant="success">在线</Badge>
                        )}
                        {!error && health?.platform && (
                            <span className="text-xs text-muted-foreground uppercase">{health.platform}</span>
                        )}
                    </div>
                </div>
            </div>

            {!error && health && (
                <>
                    <div className="hidden sm:block w-px h-8 bg-border" />
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-secondary rounded-full">
                            <AppWindow className="w-5 h-5 text-primary" />
                        </div>
                        <div>
                            <p className="text-sm font-medium leading-none mb-1">浏览器运行环境</p>
                            <div className="flex items-center gap-2">
                                {health.browser_detected ? (
                                    <Badge variant="success">已连接</Badge>
                                ) : (
                                    <Badge variant="warning">未找到</Badge>
                                )}
                                {health.user_data_detected && (
                                    <Badge variant="secondary" className="text-[10px] px-1.5 h-4">配置正常</Badge>
                                )}
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
