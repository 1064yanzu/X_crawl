"use client";

import { AlertCircle, FileSpreadsheet, FileUp, Loader2, MessageSquareText, RefreshCcw, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCommentBackfillBuilder } from "@/hooks/useCommentBackfillBuilder";
import { PlatformButton, SectionTitle } from "@/components/features/task-builder/TaskBuilderSection";
import { cn } from "@/lib/utils";

function SummaryRow({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-background/70 px-3 py-3 text-sm">
            <span className="text-muted-foreground">{label}</span>
            <span className="font-medium text-foreground">{value}</span>
        </div>
    );
}

export function CommentBackfillBuilder() {
    const {
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
        canSubmit,
        submit,
    } = useCommentBackfillBuilder();

    return (
        <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-6 p-6 sm:p-7">
                <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
                    <SectionTitle title="导入导出文件" description="把已导出的帖子文件重新导入，只针对有评论的原帖做补采。" />

                    <div className="flex flex-wrap gap-2">
                        <PlatformButton active={platform === "x"} label="𝕏 Twitter" description="需要帖子 ID 与作者账号来回补评论" onClick={() => setPlatform("x")} />
                        <PlatformButton active={platform === "weibo"} label="微博" description="需要帖子 ID（mid）与原帖链接来补抓评论树" onClick={() => setPlatform("weibo")} />
                    </div>

                    <div className="rounded-2xl border border-dashed border-border/70 bg-muted/20 p-4">
                        <label className="flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border border-border/60 bg-background/80 px-5 py-8 text-center transition-colors hover:border-primary/30 hover:bg-background">
                            <div className="rounded-2xl bg-primary/10 p-3 text-primary">
                                <UploadCloud className="h-5 w-5" />
                            </div>
                            <div>
                                <p className="font-medium text-foreground">选择 CSV 或 XLSX 导出文件</p>
                                <p className="mt-1 text-sm text-muted-foreground">支持现有任务导出文件，系统会自动过滤评论行与 0 评论帖子。</p>
                            </div>
                            <input
                                type="file"
                                accept=".csv,.xlsx"
                                className="hidden"
                                onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
                            />
                            <span className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">选择文件</span>
                        </label>

                        {file ? (
                            <div className="mt-4 flex items-center gap-3 rounded-2xl border border-border/60 bg-background px-4 py-3 text-sm">
                                <FileSpreadsheet className="h-4 w-4 text-primary" />
                                <div className="min-w-0 flex-1">
                                    <p className="truncate font-medium text-foreground">{file.name}</p>
                                    <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
                                </div>
                                <Button type="button" variant="ghost" size="sm" className="rounded-xl" onClick={() => selectFile(null)}>
                                    重新选择
                                </Button>
                            </div>
                        ) : null}
                    </div>

                    {platform === "x" ? (
                        <div className="grid gap-3 md:grid-cols-2">
                            <button
                                type="button"
                                onClick={() => setReplyDepth(1)}
                                className={cn(
                                    "rounded-2xl border px-4 py-4 text-left transition-all duration-200",
                                    replyDepth === 1 ? "border-primary/30 bg-primary/8 text-foreground shadow-sm" : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
                                )}
                            >
                                <p className="font-medium">一级评论</p>
                                <p className="mt-2 text-xs leading-5 text-muted-foreground">更快，只补采直接评论。</p>
                            </button>
                            <button
                                type="button"
                                onClick={() => setReplyDepth(2)}
                                className={cn(
                                    "rounded-2xl border px-4 py-4 text-left transition-all duration-200",
                                    replyDepth === 2 ? "border-primary/30 bg-primary/8 text-foreground shadow-sm" : "border-border/70 bg-card hover:border-primary/20 hover:bg-muted/30",
                                )}
                            >
                                <p className="font-medium">二级评论</p>
                                <p className="mt-2 text-xs leading-5 text-muted-foreground">补采评论子回复，适合更深的讨论链路分析。</p>
                            </button>
                            <div className="space-y-2 md:col-span-2">
                                <label className="text-sm font-medium text-foreground">单帖评论上限</label>
                                <Input
                                    type="number"
                                    min={0}
                                    step={1}
                                    value={maxRepliesPerTweet}
                                    onChange={(event) => setMaxRepliesPerTweet(Math.max(0, Number(event.target.value) || 0))}
                                    className="h-11 rounded-xl bg-background font-mono"
                                />
                                <p className="text-xs text-muted-foreground">`0` 表示不限制，按评论区可抓到的内容尽量补全。</p>
                            </div>
                        </div>
                    ) : (
                        <div className="rounded-2xl border border-border/60 bg-muted/20 p-4 text-sm leading-6 text-muted-foreground">
                            微博补采会基于导出文件中的原帖 `mid`、作者信息和链接，逐条进入评论接口补抓完整评论树。
                        </div>
                    )}
                </section>

                <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
                    <SectionTitle title="文件校验" description="导入前先校验文件结构，避免跑到一半才发现字段缺失。" />

                    {analyzing ? (
                        <div className="flex items-center gap-3 rounded-2xl border border-border/60 bg-background px-4 py-4 text-sm text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            正在分析导出文件结构与可补采帖子...
                        </div>
                    ) : null}

                    {analysisError ? (
                        <div className="rounded-2xl border border-red-200/70 bg-red-50/80 px-4 py-4 text-sm text-red-800 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-100">
                            <div className="flex items-start gap-3">
                                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                                <div>
                                    <p className="font-medium">文件校验失败</p>
                                    <p className="mt-1 break-words">{analysisError}</p>
                                </div>
                            </div>
                        </div>
                    ) : null}

                    {analysis ? (
                        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                            <SummaryRow label="总行数" value={`${analysis.total_rows}`} />
                            <SummaryRow label="原帖行" value={`${analysis.original_post_rows}`} />
                            <SummaryRow label="去重后原帖" value={`${analysis.unique_post_count}`} />
                            <SummaryRow label="可补采帖子" value={`${analysis.eligible_posts}`} />
                        </div>
                    ) : null}

                    {analysis ? (
                        <div className="rounded-2xl border border-border/60 bg-muted/20 p-4">
                            <div className="grid gap-3 md:grid-cols-3">
                                <SummaryRow label="跳过评论行" value={`${analysis.skipped_non_post_rows}`} />
                                <SummaryRow label="跳过 0 评论" value={`${analysis.skipped_zero_comment_posts}`} />
                                <SummaryRow label="去重条数" value={`${analysis.deduplicated_posts}`} />
                            </div>
                            <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                                <span className="rounded-full bg-background px-2.5 py-1">平台 {analysis.platform === "x" ? "𝕏 Twitter" : "微博"}</span>
                                <span className="rounded-full bg-background px-2.5 py-1">{analysis.has_platform_column ? "文件自带平台列" : "历史导出文件，按当前平台解析"}</span>
                                {analysis.skipped_invalid_posts > 0 ? <span className="rounded-full bg-background px-2.5 py-1">缺关键字段 {analysis.skipped_invalid_posts}</span> : null}
                            </div>
                        </div>
                    ) : null}
                </section>
            </div>

            <aside className="border-t border-border/50 bg-muted/15 p-6 xl:border-l xl:border-t-0 xl:p-7">
                <div className="space-y-4 xl:sticky xl:top-24">
                    <div className="rounded-[1.25rem] border border-border/60 bg-card p-5 shadow-sm">
                        <div className="flex items-center gap-2 text-primary">
                            <MessageSquareText className="h-4 w-4" />
                            <span className="text-xs font-semibold uppercase tracking-[0.18em]">Comment Backfill</span>
                        </div>
                        <h3 className="mt-3 text-lg font-semibold">提交前摘要</h3>
                        <p className="mt-2 text-sm leading-6 text-muted-foreground">用已有帖子结果做二次补采，不改原任务，生成一条新的评论补采任务。</p>

                        <div className="mt-5 space-y-3">
                            <SummaryRow label="目标平台" value={platform === "x" ? "𝕏 Twitter" : "微博"} />
                            <SummaryRow label="导入文件" value={file?.name ?? "未选择"} />
                            <SummaryRow label="可补采帖子" value={analysis ? `${analysis.eligible_posts} 条` : "--"} />
                            <SummaryRow label="补采模式" value={platform === "x" ? `${replyDepth} 级评论` : "评论树补采"} />
                        </div>

                        <Button onClick={() => void submit()} disabled={!canSubmit || submitting || analyzing} className="mt-6 h-11 w-full rounded-xl">
                            {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileUp className="mr-2 h-4 w-4" />}
                            {submitting ? "创建中..." : "创建评论补采任务"}
                        </Button>
                    </div>

                    <div className="rounded-[1.25rem] border border-border/60 bg-card p-5 shadow-sm">
                        <div className="flex items-center gap-2 text-primary">
                            <RefreshCcw className="h-4 w-4" />
                            <span className="text-xs font-semibold uppercase tracking-[0.18em]">Workflow</span>
                        </div>
                        <ul className="mt-3 space-y-3 text-sm leading-6 text-muted-foreground">
                            <li>先正常跑完帖子采集并导出。</li>
                            <li>这里导入文件后，只会挑出“原帖且评论数大于 0”的记录。</li>
                            <li>补采结果会生成新任务，方便你单独导出和复盘，不会污染原任务。</li>
                        </ul>
                    </div>
                </div>
            </aside>
        </div>
    );
}
