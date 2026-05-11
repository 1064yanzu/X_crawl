"use client";

import * as React from "react";
import { CheckCircle2, FileUp, ListOrdered, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ParseVideoIdsResult } from "@/lib/youtube-url";
import { SectionTitle } from "@/components/features/task-builder/TaskBuilderSection";

interface Props {
    text: string;
    onTextChange: (value: string) => void;
    fileName: string;
    onFileSelected: (file: File | null) => void;
    onClear: () => void;
    parsed: ParseVideoIdsResult;
}

export function YouTubeVideoUrlsFields(props: Props) {
    const fileInputRef = React.useRef<HTMLInputElement | null>(null);
    const [dragActive, setDragActive] = React.useState(false);

    const handleDrop = (event: React.DragEvent<HTMLLabelElement>) => {
        event.preventDefault();
        setDragActive(false);
        const file = event.dataTransfer.files?.[0] ?? null;
        if (file) props.onFileSelected(file);
    };

    const hasInput = props.text.trim().length > 0;
    const { ids, invalid } = props.parsed;

    return (
        <section className="space-y-4 rounded-lg border border-border bg-background p-5 shadow-sm">
            <SectionTitle
                title="视频链接批量"
                description="粘贴或导入一批 YouTube 视频链接 / 11 位 video ID，后端跳过搜索，直接抓详情与评论。"
            />

            <label className="flex flex-col gap-2 text-sm">
                <span className="font-medium text-foreground flex items-center gap-1.5">
                    <ListOrdered className="h-3.5 w-3.5" /> 视频链接或 ID（每行一个或逗号分隔）
                </span>
                <textarea
                    value={props.text}
                    onChange={(event) => props.onTextChange(event.target.value)}
                    rows={8}
                    placeholder={[
 "https://youtu.be/dQw4w9WgXcQ",
 "https://www.youtube.com/watch?v=abcdefghijk",
 "https://www.youtube.com/shorts/xyz12345678",
 "dQw4w9WgXcQ",
                    ].join("\n")}
                    className={cn(
 "w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm font-mono leading-6",
 "focus:border-primary/40 focus:ring-2 focus:ring-primary/20 outline-none resize-y",
                    )}
                />
            </label>

            <label
                onDragOver={(event) => {
                    event.preventDefault();
                    setDragActive(true);
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={handleDrop}
                className={cn(
 "flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed px-5 py-6 text-center cursor-pointer transition-all",
                    dragActive
                        ? "border-primary/60 bg-primary/8"
                        : "border-border bg-muted/20 hover:border-primary/30 hover:bg-muted/30",
                )}
            >
                <FileUp className="h-5 w-5 text-muted-foreground" />
                <div className="text-sm text-foreground">
                    拖拽文件到此，或
                    <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="mx-1 font-medium text-primary underline underline-offset-4 hover:text-primary/80"
                    >
                        点击选择
                    </button>
                    一个 <code>.txt</code> / <code>.csv</code>
                </div>
                <p className="text-xs text-muted-foreground">
                    文件内容会追加到上方文本框，每行一个链接或视频 ID。
                </p>
                <input
                    ref={fileInputRef}
                    type="file"
                    accept=".txt,.csv,text/plain,text/csv"
                    className="hidden"
                    onChange={(event) => {
                        const file = event.target.files?.[0] ?? null;
                        props.onFileSelected(file);
                        event.target.value = "";
                    }}
                />
                {props.fileName && (
                    <span className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground">
                        已导入：{props.fileName}
                    </span>
                )}
            </label>

            <div
                className={cn(
 "flex flex-col gap-2 rounded-md border px-4 py-3 text-sm",
                    ids.length > 0
                        ? "border-emerald-200/70 bg-emerald-50/70 text-emerald-800 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-100"
                        : "border-border bg-muted/20 text-muted-foreground",
                )}
            >
                <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4" />
                    <span>
                        已识别 <strong className="font-semibold">{ids.length}</strong> 个视频
                        {invalid.length > 0 ? (
                            <>
                                {" · "}
                                <span className="text-amber-700 dark:text-amber-300">
                                    {invalid.length} 行无法解析
                                </span>
                            </>
                        ) : null}
                    </span>
                    {hasInput && (
                        <button
                            type="button"
                            onClick={props.onClear}
                            className="ml-auto inline-flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                        >
                            <X className="h-3 w-3" /> 清空
                        </button>
                    )}
                </div>
                {invalid.length > 0 && (
                    <details className="text-xs text-muted-foreground">
                        <summary className="cursor-pointer select-none">展开无法解析的行</summary>
                        <ul className="mt-2 max-h-32 space-y-1 overflow-auto font-mono">
                            {invalid.slice(0, 30).map((line, index) => (
                                <li key={`${line}-${index}`} className="truncate">
                                    · {line}
                                </li>
                            ))}
                            {invalid.length > 30 && (
                                <li className="text-muted-foreground/70">
                                    …另 {invalid.length - 30} 行省略
                                </li>
                            )}
                        </ul>
                    </details>
                )}
            </div>

            <p className="text-xs text-muted-foreground">
                每个视频消耗约 <code>1 + 评论分页数</code> 个配额单位，对比关键词搜索（100 单位/次）成本极低。
            </p>
        </section>
    );
}
