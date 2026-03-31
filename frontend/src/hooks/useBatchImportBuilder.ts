"use client";

import { useCallback, useState } from "react";
import { api, type BatchImportTask, type Platform, type TaskQueueOut } from "@/services/api";

export type InputMode = "text" | "file";

export interface BatchImportState {
    inputMode: InputMode;
    setInputMode: (mode: InputMode) => void;

    // 文本输入
    textInput: string;
    setTextInput: (text: string) => void;

    // 文件上传
    selectedFile: File | null;
    setSelectedFile: (file: File | null) => void;

    // 全局默认参数
    platform: Platform;
    setPlatform: (p: Platform) => void;
    product: "Top" | "Latest" | "Photos" | "Videos";
    setProduct: (p: "Top" | "Latest" | "Photos" | "Videos") => void;
    fetchReplies: boolean;
    setFetchReplies: (fn: boolean | ((prev: boolean) => boolean)) => void;
    replyDepth: number;
    setReplyDepth: (n: number) => void;

    // 队列名称
    queueName: string;
    setQueueName: (name: string) => void;

    // 解析结果
    parsedTasks: BatchImportTask[];
    parseErrors: string[];
    parsing: boolean;
    parsed: boolean;

    // 操作
    parseText: () => void;
    parseFile: () => Promise<void>;
    removeTask: (index: number) => void;
    clearParsed: () => void;
    submitQueue: () => Promise<void>;
    submitting: boolean;
    submitResult: TaskQueueOut | null;
}

export function useBatchImportBuilder(): BatchImportState {
    const [inputMode, setInputMode] = useState<InputMode>("text");
    const [textInput, setTextInput] = useState("");
    const [selectedFile, setSelectedFile] = useState<File | null>(null);

    const [platform, setPlatform] = useState<Platform>("x");
    const [product, setProduct] = useState<"Top" | "Latest" | "Photos" | "Videos">("Top");
    const [fetchReplies, setFetchReplies] = useState(false);
    const [replyDepth, setReplyDepth] = useState(2);

    const [queueName, setQueueName] = useState("");

    const [parsedTasks, setParsedTasks] = useState<BatchImportTask[]>([]);
    const [parseErrors, setParseErrors] = useState<string[]>([]);
    const [parsing, setParsing] = useState(false);
    const [parsed, setParsed] = useState(false);

    const [submitting, setSubmitting] = useState(false);
    const [submitResult, setSubmitResult] = useState<TaskQueueOut | null>(null);

    // 解析文本输入
    const parseText = useCallback(() => {
        const lines = textInput
            .split("\n")
            .map((line) => line.trim())
            .filter((line) => line.length > 0 && !line.startsWith("#") && !line.startsWith("//"));

        if (lines.length === 0) {
            setParseErrors(["文本为空，请输入至少一个关键词"]);
            return;
        }

        // 去重
        const seen = new Set<string>();
        const tasks: BatchImportTask[] = [];
        const errors: string[] = [];

        for (const line of lines) {
            if (seen.has(line)) {
                errors.push(`关键词重复，已自动去除: "${line}"`);
                continue;
            }
            seen.add(line);
            tasks.push({
                keyword: line,
                product,
                platform,
                fetch_replies: fetchReplies,
                reply_depth: replyDepth,
                max_replies_per_tweet: 0,
                crawl_strategy: "dfs",
                start_date: null,
                end_date: null,
            });
        }

        setParsedTasks(tasks);
        setParseErrors(errors);
        setParsed(true);
    }, [textInput, product, platform, fetchReplies, replyDepth]);

    // 解析上传文件
    const parseFile = useCallback(async () => {
        if (!selectedFile) return;
        setParsing(true);
        setParseErrors([]);

        try {
            const result = await api.batchImport.parseFile({
                file: selectedFile,
                defaultPlatform: platform,
                defaultProduct: product,
                defaultFetchReplies: fetchReplies,
            });
            setParsedTasks(result.tasks);
            setParseErrors(result.errors);
            setParsed(true);
        } catch (err) {
            setParseErrors([err instanceof Error ? err.message : "文件解析失败"]);
        } finally {
            setParsing(false);
        }
    }, [selectedFile, platform, product, fetchReplies]);

    // 移除单条任务
    const removeTask = useCallback((index: number) => {
        setParsedTasks((prev) => prev.filter((_, i) => i !== index));
    }, []);

    // 清除解析结果
    const clearParsed = useCallback(() => {
        setParsedTasks([]);
        setParseErrors([]);
        setParsed(false);
        setSubmitResult(null);
    }, []);

    // 提交为队列
    const submitQueue = useCallback(async () => {
        if (parsedTasks.length === 0) return;
        setSubmitting(true);
        try {
            const result = await api.taskQueues.create({
                name: queueName || `批量导入 · ${parsedTasks.length} 个关键词`,
                tasks: parsedTasks.map((t) => ({
                    keyword: t.keyword,
                    product: t.product,
                    platform: t.platform,
                    fetch_replies: t.fetch_replies,
                    max_replies_per_tweet: t.max_replies_per_tweet,
                    reply_depth: t.reply_depth,
                    crawl_strategy: t.crawl_strategy,
                    start_date: t.start_date ?? undefined,
                    end_date: t.end_date ?? undefined,
                })),
            });
            setSubmitResult(result);
            // 提交后清空
            setParsedTasks([]);
            setParsed(false);
            setTextInput("");
            setSelectedFile(null);
        } catch (err) {
            setParseErrors([err instanceof Error ? err.message : "队列创建失败"]);
        } finally {
            setSubmitting(false);
        }
    }, [parsedTasks, queueName]);

    return {
        inputMode,
        setInputMode,
        textInput,
        setTextInput,
        selectedFile,
        setSelectedFile,
        platform,
        setPlatform,
        product,
        setProduct,
        fetchReplies,
        setFetchReplies,
        replyDepth,
        setReplyDepth,
        queueName,
        setQueueName,
        parsedTasks,
        parseErrors,
        parsing,
        parsed,
        parseText,
        parseFile,
        removeTask,
        clearParsed,
        submitQueue,
        submitting,
        submitResult,
    };
}
