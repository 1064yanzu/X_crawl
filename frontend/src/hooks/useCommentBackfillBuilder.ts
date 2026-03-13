"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { api, type CommentBackfillAnalyzeResponse, type Platform } from "@/services/api";
import { useToast } from "@/components/ui/toast";

const ALLOWED_SUFFIXES = [".csv", ".xlsx"];

export function useCommentBackfillBuilder() {
    const router = useRouter();
    const { push } = useToast();
    const [platform, setPlatform] = React.useState<Platform>("x");
    const [file, setFile] = React.useState<File | null>(null);
    const [analyzing, setAnalyzing] = React.useState(false);
    const [analysis, setAnalysis] = React.useState<CommentBackfillAnalyzeResponse | null>(null);
    const [analysisError, setAnalysisError] = React.useState<string | null>(null);
    const [submitting, setSubmitting] = React.useState(false);
    const [replyDepth, setReplyDepth] = React.useState(2);
    const [maxRepliesPerTweet, setMaxRepliesPerTweet] = React.useState(0);

    const analyzeFile = React.useCallback(async (nextFile: File, nextPlatform: Platform) => {
        setAnalyzing(true);
        setAnalysisError(null);
        try {
            const result = await api.commentBackfill.analyze(nextFile, nextPlatform);
            setAnalysis(result);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            setAnalysis(null);
            setAnalysisError(message);
        } finally {
            setAnalyzing(false);
        }
    }, []);

    React.useEffect(() => {
        if (!file) {
            setAnalysis(null);
            setAnalysisError(null);
            return;
        }
        void analyzeFile(file, platform);
    }, [analyzeFile, file, platform]);

    const selectFile = React.useCallback((nextFile: File | null) => {
        if (!nextFile) {
            setFile(null);
            setAnalysis(null);
            setAnalysisError(null);
            return;
        }
        const lowerName = nextFile.name.toLowerCase();
        if (!ALLOWED_SUFFIXES.some((suffix) => lowerName.endsWith(suffix))) {
            push({ type: "error", title: "文件格式不支持", description: "请导入 CSV 或 XLSX 导出文件。" });
            return;
        }
        setFile(nextFile);
    }, [push]);

    const submit = React.useCallback(async () => {
        if (!file) {
            push({ type: "error", title: "请先选择导出文件" });
            return;
        }
        setSubmitting(true);
        try {
            const result = await api.commentBackfill.import({
                file,
                platform,
                replyDepth,
                maxRepliesPerTweet,
            });
            push({
                type: "success",
                title: "评论补采任务已创建",
                description: `已识别 ${result.summary.eligible_posts} 条可补采帖子，正在跳转详情。`,
            });
            router.push(`/tasks/${result.task.task_id}`);
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            push({ type: "error", title: "创建评论补采任务失败", description: message });
        } finally {
            setSubmitting(false);
        }
    }, [file, maxRepliesPerTweet, platform, push, replyDepth, router]);

    return {
        platform,
        setPlatform,
        file,
        selectFile,
        analyzing,
        analysis,
        analysisError,
        submitting,
        replyDepth,
        setReplyDepth,
        maxRepliesPerTweet,
        setMaxRepliesPerTweet,
        canSubmit: Boolean(file && analysis && !analysisError && analysis.eligible_posts > 0),
        submit,
    };
}
