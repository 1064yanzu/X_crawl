"use client";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Loader2, Pause, ShieldAlert, StopCircle, XCircle } from "lucide-react";

type Props = {
    status: string;
    riskState: string;
};

export function TaskStatusBadge({ status, riskState }: Props) {
    const isRunning = status === "running" || status === "pending";
    const isPaused = status === "paused";
    const isRiskPaused = isPaused && riskState !== "none";

    if (isRunning) {
        return (
            <Badge className="bg-blue-500/10 text-blue-600 hover:bg-blue-500/20 text-sm py-1 border-0">
                <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> 正在执行
            </Badge>
        );
    }
    if (isRiskPaused) {
        return (
            <Badge className="bg-orange-500/10 text-orange-700 hover:bg-orange-500/20 text-sm py-1 border-0">
                <ShieldAlert className="w-4 h-4 mr-1.5" /> 风控暂停 ({riskState})
            </Badge>
        );
    }
    if (isPaused) {
        return (
            <Badge className="bg-amber-500/10 text-amber-600 hover:bg-amber-500/20 text-sm py-1 border-0">
                <Pause className="w-4 h-4 mr-1.5" /> 已暂停
            </Badge>
        );
    }
    if (status === "stopped") {
        return (
            <Badge className="bg-gray-500/10 text-gray-600 hover:bg-gray-500/20 text-sm py-1 border-0">
                <StopCircle className="w-4 h-4 mr-1.5" /> 已终止
            </Badge>
        );
    }
    if (status === "done") {
        return (
            <Badge className="bg-green-500/10 text-green-600 hover:bg-green-500/20 text-sm py-1 border-0">
                <CheckCircle2 className="w-4 h-4 mr-1.5" /> 任务完成
            </Badge>
        );
    }
    if (status === "failed") {
        return (
            <Badge className="bg-red-500/10 text-red-600 hover:bg-red-500/20 text-sm py-1 border-0">
                <XCircle className="w-4 h-4 mr-1.5" /> 任务失败
            </Badge>
        );
    }
    return <Badge variant="outline">{status}</Badge>;
}

