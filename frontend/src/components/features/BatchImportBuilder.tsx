"use client";

import * as React from "react";
import {
    AlertCircle,
    CheckCircle2,
    Clock,
    FileSpreadsheet,
    FileText,
    Film,
    Image,
    ListOrdered,
    Loader2,
    MessageSquare,
    Trash2,
    TrendingUp,
    Upload,
    X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useBatchImportBuilder, type InputMode } from "@/hooks/useBatchImportBuilder";
import { PlatformButton, SectionTitle } from "@/components/features/task-builder/TaskBuilderSection";
import type { BatchImportTask } from "@/services/api";

const PRODUCT_TABS = [
    { value: "Top" as const, label: "最热", icon: TrendingUp },
    { value: "Latest" as const, label: "最新", icon: Clock },
    { value: "Photos" as const, label: "图片", icon: Image },
    { value: "Videos" as const, label: "视频", icon: Film },
];

const INPUT_MODES: Array<{ value: InputMode; label: string; description: string; icon: React.ElementType }> = [
    { value: "text", label: "文本粘贴", description: "每行一个关键词", icon: FileText },
    { value: "file", label: "文件上传", description: "CSV / Excel", icon: FileSpreadsheet },
];

const ACCEPTED_EXTENSIONS = ".csv,.txt,.xlsx,.xls";

export function BatchImportBuilder() {
    const state = useBatchImportBuilder();

    return (
        <div className="space-y-6 p-6 sm:p-7">
            {/* 成功提示 */}
            {state.submitResult && (
                <SuccessBanner
                    total={state.submitResult.total_tasks}
                    queueName={state.submitResult.name}
                    onDismiss={() => state.clearParsed()}
                />
            )}

            {/* 全局参数 */}
            <GlobalParamsSection state={state} />

            {/* 输入方式 */}
            <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
                <SectionTitle title="关键词来源" description="选择输入方式，批量导入待采集的关键词列表。" />

                <div className="grid gap-3 grid-cols-2">
                    {INPUT_MODES.map((mode) => {
                        const active = state.inputMode === mode.value;
                        const Icon = mode.icon;
                        return (
                            <button
                                key={mode.value}
                                type="button"
                                onClick={() => { state.setInputMode(mode.value); state.clearParsed(); }}
                                className={cn(
                                    "flex h-full w-full flex-col items-start justify-start rounded-2xl border px-4 py-4 text-left transition-all duration-200",
                                    active
                                        ? "border-primary/30 bg-primary/8 text-foreground shadow-sm"
                                        : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
                                )}
                            >
                                <div className="flex items-center gap-2">
                                    <div className={cn("rounded-xl p-2", active ? "bg-primary/12 text-primary" : "bg-muted text-muted-foreground")}>
                                        <Icon className="h-4 w-4" />
                                    </div>
                                    <span className="font-medium">{mode.label}</span>
                                </div>
                                <p className="mt-3 text-xs leading-5 text-muted-foreground">{mode.description}</p>
                            </button>
                        );
                    })}
                </div>

                {state.inputMode === "text" ? <TextInputArea state={state} /> : <FileUploadArea state={state} />}
            </section>

            {/* 解析结果预览 */}
            {state.parsed && state.parsedTasks.length > 0 && (
                <ParsedPreviewSection state={state} />
            )}

            {/* 解析错误 */}
            {state.parseErrors.length > 0 && (
                <div className="rounded-2xl border border-amber-200/70 bg-amber-50/70 p-4 dark:border-amber-500/20 dark:bg-amber-500/10">
                    <div className="flex items-start gap-2">
                        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                        <div className="space-y-1 text-sm text-amber-900 dark:text-amber-100">
                            {state.parseErrors.map((err, i) => (
                                <p key={i}>{err}</p>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

/* ── 全局参数区域 ──────────────────────────────────────────── */

function GlobalParamsSection({ state }: { state: ReturnType<typeof useBatchImportBuilder> }) {
    return (
        <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
            <SectionTitle title="全局默认参数" description="对批量导入的所有任务统一设置平台、内容模式与基础参数。文件中指定的值会覆盖这里。" />

            {/* 平台选择 */}
            <div className="flex flex-wrap gap-2">
                <PlatformButton active={state.platform === "x"} label="𝕏 Twitter" description="支持高级搜索与时间切片" onClick={() => state.setPlatform("x")} />
                <PlatformButton active={state.platform === "weibo"} label="微博" description="适合指定时间范围批量回采" onClick={() => state.setPlatform("weibo")} />
            </div>

            {/* 内容模式 */}
            <div className="grid gap-2 sm:grid-cols-4">
                {PRODUCT_TABS.map(({ value, label, icon: Icon }) => {
                    const active = state.product === value;
                    return (
                        <button
                            key={value}
                            type="button"
                            onClick={() => state.setProduct(value)}
                            className={cn(
                                "flex w-full items-center gap-2 rounded-2xl border px-4 py-3 text-left transition-all duration-200",
                                active
                                    ? "border-primary/30 bg-primary/8 text-foreground shadow-sm"
                                    : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
                            )}
                        >
                            <div className={cn("rounded-xl p-1.5", active ? "bg-primary/12 text-primary" : "bg-muted text-muted-foreground")}>
                                <Icon className="h-3.5 w-3.5" />
                            </div>
                            <span className="text-sm font-medium">{label}</span>
                        </button>
                    );
                })}
            </div>

            {/* 评论 */}
            <div className="grid gap-4 lg:grid-cols-1">
                <div className="space-y-3">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <MessageSquare className="h-4 w-4 text-primary" />
                            <span className="text-sm font-medium text-foreground">评论抓取</span>
                        </div>
                        <button
                            type="button"
                            aria-pressed={state.fetchReplies}
                            onClick={() => state.setFetchReplies((v) => !v)}
                            className={cn(
                                "inline-flex h-9 shrink-0 whitespace-nowrap items-center rounded-full border px-3 text-sm font-medium transition-all",
                                state.fetchReplies
                                    ? "border-primary/20 bg-primary text-primary-foreground"
                                    : "border-border/70 bg-background text-muted-foreground hover:text-foreground",
                            )}
                        >
                            {state.fetchReplies ? "已开启" : "关闭"}
                        </button>
                    </div>
                    {state.fetchReplies && (
                        <div className="flex gap-2">
                            {[1, 2].map((depth) => (
                                <button
                                    key={depth}
                                    type="button"
                                    onClick={() => state.setReplyDepth(depth)}
                                    className={cn(
                                        "rounded-xl border px-3 py-1.5 text-sm transition-all",
                                        state.replyDepth === depth
                                            ? "border-primary/30 bg-primary/8 font-medium text-foreground"
                                            : "border-border/70 text-muted-foreground hover:text-foreground",
                                    )}
                                >
                                    {depth === 1 ? "一级" : "二级"}评论
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </section>
    );
}

/* ── 文本输入区域 ──────────────────────────────────────────── */

function TextInputArea({ state }: { state: ReturnType<typeof useBatchImportBuilder> }) {
    const lineCount = state.textInput
        .split("\n")
        .filter((l) => l.trim().length > 0 && !l.trim().startsWith("#") && !l.trim().startsWith("//"))
        .length;

    return (
        <div className="space-y-3">
            <div className="relative">
                <textarea
                    value={state.textInput}
                    onChange={(e) => state.setTextInput(e.target.value)}
                    placeholder={"每行输入一个关键词，可用 # 注释行\n\n例如：\nPython教程\n机器学习入门\n# 这一行会被跳过\n深度学习框架对比"}
                    rows={10}
                    className="w-full resize-y rounded-2xl border border-border/60 bg-background px-4 py-3 text-sm leading-6 placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
                {lineCount > 0 && (
                    <span className="absolute bottom-3 right-3 rounded-full bg-muted/80 px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                        {lineCount} 个关键词
                    </span>
                )}
            </div>
            <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">支持 # 或 // 开头注释行，自动去重</p>
                <Button
                    type="button"
                    onClick={state.parseText}
                    disabled={lineCount === 0}
                    className="rounded-xl"
                >
                    解析关键词
                </Button>
            </div>
        </div>
    );
}

/* ── 文件上传区域 ──────────────────────────────────────────── */

function FileUploadArea({ state }: { state: ReturnType<typeof useBatchImportBuilder> }) {
    const inputRef = React.useRef<HTMLInputElement>(null);
    const [dragOver, setDragOver] = React.useState(false);

    const handleFileChange = (file: File | null) => {
        state.setSelectedFile(file);
        state.clearParsed();
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFileChange(file);
    };

    return (
        <div className="space-y-3">
            <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
                className={cn(
                    "cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition-all duration-200",
                    dragOver
                        ? "border-primary/50 bg-primary/5"
                        : "border-border/60 bg-muted/10 hover:border-primary/30 hover:bg-muted/20",
                )}
            >
                <input
                    ref={inputRef}
                    type="file"
                    accept={ACCEPTED_EXTENSIONS}
                    className="hidden"
                    onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
                />
                <Upload className="mx-auto h-8 w-8 text-muted-foreground/60" />
                <p className="mt-3 text-sm font-medium text-foreground">
                    拖拽文件到此处，或<span className="text-primary">点击选择</span>
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                    支持 CSV、TXT、Excel（.xlsx）文件
                </p>
            </div>

            {state.selectedFile && (
                <div className="flex items-center justify-between rounded-2xl border border-border/60 bg-background/80 px-4 py-3">
                    <div className="flex items-center gap-2 min-w-0">
                        <FileSpreadsheet className="h-4 w-4 shrink-0 text-primary" />
                        <span className="truncate text-sm font-medium">{state.selectedFile.name}</span>
                        <span className="shrink-0 text-xs text-muted-foreground">
                            ({(state.selectedFile.size / 1024).toFixed(1)} KB)
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="rounded-xl text-muted-foreground hover:text-destructive"
                            onClick={(e) => { e.stopPropagation(); handleFileChange(null); }}
                        >
                            <X className="h-4 w-4" />
                        </Button>
                        <Button
                            type="button"
                            onClick={() => void state.parseFile()}
                            disabled={state.parsing}
                            className="rounded-xl"
                        >
                            {state.parsing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                            {state.parsing ? "解析中..." : "解析文件"}
                        </Button>
                    </div>
                </div>
            )}

            {/* CSV 格式说明 */}
            <details className="group rounded-2xl border border-border/60 bg-muted/20">
                <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-foreground transition-colors hover:text-primary">
                    CSV / Excel 格式说明
                </summary>
                <div className="border-t border-border/50 px-4 pb-4 pt-3 text-xs leading-6 text-muted-foreground">
                    <p className="mb-2">当文件第一行包含 <code className="rounded bg-muted px-1 py-0.5">keyword</code> 表头时，自动识别为结构化导入，支持以下列名：</p>
                    <div className="overflow-x-auto rounded-xl border border-border/50">
                        <table className="w-full text-left">
                            <thead>
                                <tr className="border-b border-border/50 bg-muted/30">
                                    <th className="px-3 py-2">列名</th>
                                    <th className="px-3 py-2">说明</th>
                                    <th className="px-3 py-2">默认值</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border/30">
                                <tr><td className="px-3 py-1.5 font-mono">keyword</td><td className="px-3 py-1.5">关键词（必须）</td><td className="px-3 py-1.5">-</td></tr>
                                <tr><td className="px-3 py-1.5 font-mono">product</td><td className="px-3 py-1.5">Top / Latest / Photos / Videos</td><td className="px-3 py-1.5">Top</td></tr>
                                <tr><td className="px-3 py-1.5 font-mono">platform</td><td className="px-3 py-1.5">x / weibo</td><td className="px-3 py-1.5">x</td></tr>
                                <tr><td className="px-3 py-1.5 font-mono">fetch_replies</td><td className="px-3 py-1.5">是否抓评论（true/false）</td><td className="px-3 py-1.5">false</td></tr>
                                <tr><td className="px-3 py-1.5 font-mono">start_date</td><td className="px-3 py-1.5">开始日期 YYYY-MM-DD</td><td className="px-3 py-1.5">-</td></tr>
                                <tr><td className="px-3 py-1.5 font-mono">end_date</td><td className="px-3 py-1.5">结束日期 YYYY-MM-DD</td><td className="px-3 py-1.5">-</td></tr>
                            </tbody>
                        </table>
                    </div>
                    <p className="mt-2">若<strong>无表头</strong>，则将每行第一个字段视为关键词，其余参数使用上方全局设置。</p>
                </div>
            </details>
        </div>
    );
}

/* ── 解析结果预览 ──────────────────────────────────────────── */

function ParsedPreviewSection({ state }: { state: ReturnType<typeof useBatchImportBuilder> }) {
    return (
        <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
            <div className="flex items-start justify-between">
                <SectionTitle
                    title="任务预览"
                    description={`共解析出 ${state.parsedTasks.length} 个采集任务，提交后将创建为顺序执行队列。`}
                />
                <Button
                    type="button"
                    variant="ghost"
                    className="rounded-xl text-muted-foreground"
                    onClick={state.clearParsed}
                >
                    清空
                </Button>
            </div>

            {/* 队列名称 */}
            <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">队列名称</label>
                <Input
                    value={state.queueName}
                    onChange={(e) => state.setQueueName(e.target.value)}
                    placeholder={`批量导入 · ${state.parsedTasks.length} 个关键词`}
                    className="h-11 rounded-xl bg-background"
                />
            </div>

            {/* 任务列表 */}
            <div className="max-h-[28rem] space-y-2 overflow-y-auto pr-1">
                {state.parsedTasks.map((task, index) => (
                    <TaskRow key={`${task.keyword}-${index}`} task={task} index={index} onRemove={() => state.removeTask(index)} />
                ))}
            </div>

            {/* 提交按钮 */}
            <div className="flex items-center justify-between border-t border-border/50 pt-4">
                <p className="text-sm text-muted-foreground">
                    {state.parsedTasks.length} 个任务将按顺序执行
                </p>
                <Button
                    type="button"
                    className="rounded-xl"
                    onClick={() => void state.submitQueue()}
                    disabled={state.parsedTasks.length === 0 || state.submitting}
                >
                    {state.submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ListOrdered className="mr-2 h-4 w-4" />}
                    {state.submitting ? "创建中..." : "创建任务队列"}
                </Button>
            </div>
        </section>
    );
}

/* ── 单行任务卡片 ──────────────────────────────────────────── */

function TaskRow({ task, index, onRemove }: { task: BatchImportTask; index: number; onRemove: () => void }) {
    const productLabel = { Top: "最热", Latest: "最新", Photos: "图片", Videos: "视频" }[task.product];
    const platformLabel = task.platform === "x" ? "𝕏" : "微博";

    return (
        <div className="flex items-center gap-3 rounded-2xl border border-border/60 bg-background/85 px-4 py-3 shadow-sm transition-colors hover:bg-muted/20">
            <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-full bg-primary/10 px-2 text-xs font-semibold text-primary">
                {index + 1}
            </span>
            <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-foreground">{task.keyword}</p>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <span className="rounded-md bg-muted/60 px-1.5 py-0.5">{platformLabel}</span>
                    <span className="rounded-md bg-muted/60 px-1.5 py-0.5">{productLabel}</span>
                    {task.fetch_replies && <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-primary">评论 {task.reply_depth} 层</span>}
                    {task.start_date && <span className="rounded-md bg-muted/60 px-1.5 py-0.5">{task.start_date}</span>}
                    {task.end_date && <span className="rounded-md bg-muted/60 px-1.5 py-0.5">~ {task.end_date}</span>}
                </div>
            </div>
            <Button type="button" variant="ghost" size="icon" className="shrink-0 rounded-xl text-muted-foreground hover:text-destructive" onClick={onRemove}>
                <Trash2 className="h-4 w-4" />
            </Button>
        </div>
    );
}

/* ── 成功提示 ──────────────────────────────────────────────── */

function SuccessBanner({ total, queueName, onDismiss }: { total: number; queueName: string; onDismiss: () => void }) {
    return (
        <div className="flex items-start gap-3 rounded-2xl border border-green-200/70 bg-green-50/70 p-4 dark:border-green-500/20 dark:bg-green-500/10">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-green-600 dark:text-green-400" />
            <div className="flex-1">
                <p className="font-medium text-green-900 dark:text-green-100">
                    队列创建成功
                </p>
                <p className="mt-1 text-sm text-green-800 dark:text-green-200">
                    「{queueName}」已创建，共 {total} 个任务将按顺序执行。可前往任务列表查看进度。
                </p>
            </div>
            <Button type="button" variant="ghost" size="icon" className="shrink-0 rounded-xl" onClick={onDismiss}>
                <X className="h-4 w-4" />
            </Button>
        </div>
    );
}
