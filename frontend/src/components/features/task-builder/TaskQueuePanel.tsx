import { ArrowDown, ArrowUp, ListOrdered, Loader2, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { TaskQueueDraft } from "@/hooks/useTaskQueueBuilder";
import { SectionTitle } from "@/components/features/task-builder/TaskBuilderSection";

export function TaskQueuePanel({
    queueName,
    onQueueNameChange,
    drafts,
    onAddCurrent,
    onMove,
    onRemove,
    onClear,
    onSubmit,
    submitting,
}: {
    queueName: string;
    onQueueNameChange: (value: string) => void;
    drafts: TaskQueueDraft[];
    onAddCurrent: () => void;
    onMove: (draftId: string, direction: -1 | 1) => void;
    onRemove: (draftId: string) => void;
    onClear: () => void;
    onSubmit: () => void;
    submitting: boolean;
}) {
    return (
        <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div className="flex-1 space-y-4">
                    <SectionTitle title="任务队列" description="把当前配置加入草稿篮子，后端会严格按顺序一个一个执行。" />
                    <div className="space-y-2">
                        <label className="text-sm font-medium text-foreground">队列名称</label>
                        <Input
                            value={queueName}
                            onChange={(event) => onQueueNameChange(event.target.value)}
                            placeholder="例如：品牌监测 · 3 月批次"
                            className="h-11 rounded-xl bg-background"
                        />
                    </div>
                </div>
                <Button type="button" variant="outline" className="h-11 rounded-xl" onClick={onAddCurrent}>
                    <Plus className="mr-2 h-4 w-4" />
                    把当前配置加入队列
                </Button>
            </div>

            <div className="rounded-2xl border border-border/60 bg-muted/20 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                        <p className="text-sm font-medium text-foreground">顺序执行清单</p>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">
                            当前共有 {drafts.length} 个待执行项。创建后，第 2 项开始会等待前序任务结束再自动接力。
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button type="button" variant="ghost" className="rounded-xl" onClick={onClear} disabled={drafts.length === 0 || submitting}>
                            清空
                        </Button>
                        <Button type="button" className="rounded-xl" onClick={onSubmit} disabled={drafts.length === 0 || submitting}>
                            {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ListOrdered className="mr-2 h-4 w-4" />}
                            {submitting ? "创建中..." : "按顺序开始整组任务"}
                        </Button>
                    </div>
                </div>

                {drafts.length === 0 ? (
                    <div className="mt-4 rounded-2xl border border-dashed border-border/70 bg-background/70 px-4 py-8 text-center text-sm text-muted-foreground">
                        先在上方配置一个任务，然后点击“把当前配置加入队列”。
                    </div>
                ) : (
                    <div className="mt-4 space-y-3">
                        {drafts.map((draft, index) => (
                            <div key={draft.draft_id} className="rounded-2xl border border-border/60 bg-background/85 p-4 shadow-sm">
                                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                    <div className="min-w-0 flex-1">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-full bg-primary/10 px-2.5 text-xs font-semibold text-primary">
                                                {index + 1}
                                            </span>
                                            <p className="line-clamp-2 text-sm font-semibold text-foreground">{draft.keyword}</p>
                                        </div>
                                        <p className="mt-2 text-xs leading-5 text-muted-foreground">{draft.summary}</p>
                                    </div>
                                    <div className="flex items-center gap-1 self-end lg:self-start">
                                        <Button type="button" variant="ghost" size="icon" className="rounded-xl" onClick={() => onMove(draft.draft_id, -1)} disabled={index === 0 || submitting}>
                                            <ArrowUp className="h-4 w-4" />
                                        </Button>
                                        <Button type="button" variant="ghost" size="icon" className="rounded-xl" onClick={() => onMove(draft.draft_id, 1)} disabled={index === drafts.length - 1 || submitting}>
                                            <ArrowDown className="h-4 w-4" />
                                        </Button>
                                        <Button type="button" variant="ghost" size="icon" className="rounded-xl text-destructive hover:text-destructive" onClick={() => onRemove(draft.draft_id)} disabled={submitting}>
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </section>
    );
}
