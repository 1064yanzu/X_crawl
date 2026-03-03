"use client";
import * as React from "react";
import { Input } from "@/components/ui/input";
import { ChevronDown, SlidersHorizontal, Search, AtSign, Filter, BarChart3, Calendar } from "lucide-react";

// ── 完整的高级搜索参数（对齐 X 原生高级搜索面板全部字段） ──
export interface AdvancedSearchParams {
    // Words 区域
    allWords: string;       // All of these words
    exactPhrase: string;    // This exact phrase
    anyWords: string;       // Any of these words
    noneWords: string;      // None of these words
    hashtags: string;       // These hashtags
    // Language
    lang: string;
    // Accounts 区域
    fromAccounts: string;   // From these accounts
    toAccounts: string;     // To these accounts
    mentionAccounts: string; // Mentioning these accounts
    // Filters 区域
    replyFilter: "off" | "include" | "only"; // Replies
    linkFilter: "off" | "include" | "only";  // Links
    // Engagement 区域
    minReplies: string;
    minFaves: string;
    minRetweets: string;
    // Dates 区域
    since: string;          // From date (YYYY-MM-DD)
    until: string;          // To date (YYYY-MM-DD)
}

export const DEFAULT_ADVANCED_PARAMS: AdvancedSearchParams = {
    allWords: "",
    exactPhrase: "",
    anyWords: "",
    noneWords: "",
    hashtags: "",
    lang: "",
    fromAccounts: "",
    toAccounts: "",
    mentionAccounts: "",
    replyFilter: "off",
    linkFilter: "off",
    minReplies: "",
    minFaves: "",
    minRetweets: "",
    since: "",
    until: "",
};

/**
 * 将高级搜索参数构建为 X 搜索操作符字符串
 */
export function buildAdvancedQuery(params: AdvancedSearchParams): string {
    const parts: string[] = [];

    // All of these words（直接追加到查询）
    if (params.allWords.trim()) {
        parts.push(params.allWords.trim());
    }

    // Exact phrase → "phrase"
    if (params.exactPhrase.trim()) {
        parts.push(`"${params.exactPhrase.trim()}"`);
    }

    // Any of these words → word1 OR word2 OR word3
    if (params.anyWords.trim()) {
        const words = params.anyWords.trim().split(/\s+/).filter(Boolean);
        if (words.length > 1) {
            parts.push(`(${words.join(" OR ")})`);
        } else if (words.length === 1) {
            parts.push(words[0]);
        }
    }

    // None of these words → -word1 -word2
    if (params.noneWords.trim()) {
        const words = params.noneWords.trim().split(/\s+/).filter(Boolean);
        for (const w of words) {
            parts.push(`-${w}`);
        }
    }

    // Hashtags → #tag1 #tag2
    if (params.hashtags.trim()) {
        const tags = params.hashtags.trim().split(/\s+/).filter(Boolean);
        for (const tag of tags) {
            parts.push(tag.startsWith("#") ? tag : `#${tag}`);
        }
    }

    // Language
    if (params.lang) {
        parts.push(`lang:${params.lang}`);
    }

    // From accounts → from:user1 OR from:user2
    if (params.fromAccounts.trim()) {
        const accounts = params.fromAccounts.trim().split(/[\s,]+/).filter(Boolean);
        const fromParts = accounts.map(a => `from:${a.replace(/^@/, "")}`);
        if (fromParts.length > 1) {
            parts.push(`(${fromParts.join(" OR ")})`);
        } else if (fromParts.length === 1) {
            parts.push(fromParts[0]);
        }
    }

    // To accounts → to:user1 OR to:user2
    if (params.toAccounts.trim()) {
        const accounts = params.toAccounts.trim().split(/[\s,]+/).filter(Boolean);
        const toParts = accounts.map(a => `to:${a.replace(/^@/, "")}`);
        if (toParts.length > 1) {
            parts.push(`(${toParts.join(" OR ")})`);
        } else if (toParts.length === 1) {
            parts.push(toParts[0]);
        }
    }

    // Mentioning accounts → @user1 @user2
    if (params.mentionAccounts.trim()) {
        const accounts = params.mentionAccounts.trim().split(/[\s,]+/).filter(Boolean);
        for (const a of accounts) {
            parts.push(a.startsWith("@") ? a : `@${a}`);
        }
    }

    // Reply filter
    if (params.replyFilter === "only") {
        parts.push("filter:replies");
    } else if (params.replyFilter === "include") {
        // 默认就是包含，不需要额外操作符
    }

    // Link filter
    if (params.linkFilter === "only") {
        parts.push("filter:links");
    } else if (params.linkFilter === "include") {
        // 默认就是包含
    }

    // Engagement
    if (params.minReplies && Number(params.minReplies) > 0) {
        parts.push(`min_replies:${params.minReplies}`);
    }
    if (params.minFaves && Number(params.minFaves) > 0) {
        parts.push(`min_faves:${params.minFaves}`);
    }
    if (params.minRetweets && Number(params.minRetweets) > 0) {
        parts.push(`min_retweets:${params.minRetweets}`);
    }

    // Dates
    if (params.since) {
        parts.push(`since:${params.since}`);
    }
    if (params.until) {
        parts.push(`until:${params.until}`);
    }

    return parts.join(" ");
}

/**
 * 检查高级搜索参数是否有任何非空值
 */
export function hasActiveFilters(params: AdvancedSearchParams): boolean {
    return !!(
        params.allWords || params.exactPhrase || params.anyWords ||
        params.noneWords || params.hashtags || params.lang ||
        params.fromAccounts || params.toAccounts || params.mentionAccounts ||
        params.replyFilter !== "off" || params.linkFilter !== "off" ||
        params.minReplies || params.minFaves || params.minRetweets ||
        params.since || params.until
    );
}

// ── 语言列表（对齐 X 高级搜索面板）──
const LANGUAGES = [
    { value: "", label: "无限制 (Any)" },
    { value: "zh", label: "中文 (Chinese)" },
    { value: "en", label: "英文 (English)" },
    { value: "ja", label: "日文 (Japanese)" },
    { value: "ko", label: "韩文 (Korean)" },
    { value: "ar", label: "阿拉伯语 (Arabic)" },
    { value: "bn", label: "孟加拉语 (Bangla)" },
    { value: "bg", label: "保加利亚语 (Bulgarian)" },
    { value: "ca", label: "加泰罗尼亚语 (Catalan)" },
    { value: "hr", label: "克罗地亚语 (Croatian)" },
    { value: "cs", label: "捷克语 (Czech)" },
    { value: "da", label: "丹麦语 (Danish)" },
    { value: "nl", label: "荷兰语 (Dutch)" },
    { value: "fi", label: "芬兰语 (Finnish)" },
    { value: "fr", label: "法语 (French)" },
    { value: "de", label: "德语 (German)" },
    { value: "el", label: "希腊语 (Greek)" },
    { value: "gu", label: "古吉拉特语 (Gujarati)" },
    { value: "he", label: "希伯来语 (Hebrew)" },
    { value: "hi", label: "印地语 (Hindi)" },
    { value: "hu", label: "匈牙利语 (Hungarian)" },
    { value: "id", label: "印尼语 (Indonesian)" },
    { value: "it", label: "意大利语 (Italian)" },
    { value: "kn", label: "卡纳达语 (Kannada)" },
    { value: "mr", label: "马拉地语 (Marathi)" },
    { value: "no", label: "挪威语 (Norwegian)" },
    { value: "fa", label: "波斯语 (Persian)" },
    { value: "pl", label: "波兰语 (Polish)" },
    { value: "pt", label: "葡萄牙语 (Portuguese)" },
    { value: "ro", label: "罗马尼亚语 (Romanian)" },
    { value: "ru", label: "俄语 (Russian)" },
    { value: "sr", label: "塞尔维亚语 (Serbian)" },
    { value: "sk", label: "斯洛伐克语 (Slovak)" },
    { value: "es", label: "西班牙语 (Spanish)" },
    { value: "sv", label: "瑞典语 (Swedish)" },
    { value: "ta", label: "泰米尔语 (Tamil)" },
    { value: "th", label: "泰语 (Thai)" },
    { value: "tr", label: "土耳其语 (Turkish)" },
    { value: "uk", label: "乌克兰语 (Ukrainian)" },
    { value: "ur", label: "乌尔都语 (Urdu)" },
    { value: "vi", label: "越南语 (Vietnamese)" },
] as const;

// ── 区域标题组件 ──
function SectionHeader({ icon: Icon, title }: { icon: React.ElementType; title: string }) {
    return (
        <div className="flex items-center gap-2 pb-1">
            <Icon className="w-3.5 h-3.5 text-primary/70" />
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</span>
        </div>
    );
}

// ── 输入框组件（统一样式）──
function FieldInput({
    label, hint, id, ...inputProps
}: { label: string; hint?: string; id: string } & React.InputHTMLAttributes<HTMLInputElement>) {
    return (
        <div className="space-y-1.5">
            <label htmlFor={id} className="text-xs font-medium block text-foreground/80">{label}</label>
            <Input id={id} className="h-9" {...inputProps} />
            {hint && <p className="text-[11px] text-muted-foreground/70 leading-tight">{hint}</p>}
        </div>
    );
}

// ── 三态筛选器组件 ──
function TriStateFilter({
    label, value, onChange,
}: { label: string; value: "off" | "include" | "only"; onChange: (v: "off" | "include" | "only") => void }) {
    const options = [
        { v: "off" as const, l: "关闭" },
        { v: "include" as const, l: "包含" },
        { v: "only" as const, l: "仅显示" },
    ];
    return (
        <div className="space-y-1.5">
            <span className="text-xs font-medium text-foreground/80">{label}</span>
            <div className="flex gap-1 p-0.5 bg-muted/50 rounded-lg border border-border/30">
                {options.map(opt => (
                    <button
                        key={opt.v}
                        type="button"
                        onClick={() => onChange(opt.v)}
                        className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium transition-all duration-200 cursor-pointer ${
                            value === opt.v
                                ? "bg-background text-foreground shadow-sm border border-border/60"
                                : "text-muted-foreground hover:text-foreground"
                        }`}
                    >
                        {opt.l}
                    </button>
                ))}
            </div>
        </div>
    );
}

// ══════════════════════════════════════════════════════════════════
//  主面板组件
// ══════════════════════════════════════════════════════════════════

interface Props {
    params: AdvancedSearchParams;
    onChange: (params: AdvancedSearchParams) => void;
    isOpen: boolean;
    onToggle: () => void;
}

export function AdvancedSearchPanel({ params, onChange, isOpen, onToggle }: Props) {
    const update = (key: keyof AdvancedSearchParams, value: string) => {
        onChange({ ...params, [key]: value });
    };

    const activeCount = [
        params.allWords, params.exactPhrase, params.anyWords, params.noneWords, params.hashtags,
        params.lang, params.fromAccounts, params.toAccounts, params.mentionAccounts,
        params.replyFilter !== "off" ? "1" : "", params.linkFilter !== "off" ? "1" : "",
        params.minReplies, params.minFaves, params.minRetweets,
        params.since, params.until,
    ].filter(Boolean).length;

    return (
        <div className="border rounded-xl bg-card overflow-hidden transition-all duration-300">
            <button
                type="button"
                onClick={onToggle}
                className="w-full flex items-center justify-between p-4 bg-muted/20 hover:bg-muted/40 transition-colors"
            >
                <div className="flex items-center gap-2 font-medium text-sm text-foreground">
                    <SlidersHorizontal className="w-4 h-4 text-primary" />
                    高级搜索
                    {activeCount > 0 && (
                        <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-primary text-primary-foreground text-[11px] font-bold">
                            {activeCount}
                        </span>
                    )}
                </div>
                <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`} />
            </button>

            <div className={`grid transition-all duration-300 ease-in-out ${isOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}>
                <div className="overflow-hidden">
                    <div className="p-5 pt-3 border-t space-y-5">

                        {/* ── Words 区域 ── */}
                        <div className="space-y-3">
                            <SectionHeader icon={Search} title="关键词" />
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                <FieldInput
                                    id="allWords" label="包含全部这些词"
                                    placeholder="what's happening"
                                    hint="搜索结果将同时包含这些词"
                                    value={params.allWords}
                                    onChange={(e) => update("allWords", (e.target as HTMLInputElement).value)}
                                />
                                <FieldInput
                                    id="exactPhrase" label="包含精确短语"
                                    placeholder="happy hour"
                                    hint='搜索结果将包含完整短语 "happy hour"'
                                    value={params.exactPhrase}
                                    onChange={(e) => update("exactPhrase", (e.target as HTMLInputElement).value)}
                                />
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                <FieldInput
                                    id="anyWords" label="包含任意这些词"
                                    placeholder="cats dogs"
                                    hint='包含 "cats" 或 "dogs"（或两者）'
                                    value={params.anyWords}
                                    onChange={(e) => update("anyWords", (e.target as HTMLInputElement).value)}
                                />
                                <FieldInput
                                    id="noneWords" label="排除这些词"
                                    placeholder="广告 推广"
                                    hint="搜索结果不会包含这些词"
                                    value={params.noneWords}
                                    onChange={(e) => update("noneWords", (e.target as HTMLInputElement).value)}
                                />
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                <FieldInput
                                    id="hashtags" label="包含这些 Hashtag"
                                    placeholder="#ThrowbackThursday"
                                    hint="搜索包含指定 hashtag 的推文"
                                    value={params.hashtags}
                                    onChange={(e) => update("hashtags", (e.target as HTMLInputElement).value)}
                                />
                                <div className="space-y-1.5">
                                    <label htmlFor="lang" className="text-xs font-medium block text-foreground/80">语言</label>
                                    <select
                                        id="lang"
                                        className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                                        value={params.lang}
                                        onChange={(e) => update("lang", e.target.value)}
                                    >
                                        {LANGUAGES.map(l => (
                                            <option key={l.value} value={l.value}>{l.label}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                        </div>

                        {/* ── Accounts 区域 ── */}
                        <div className="space-y-3 pt-3 border-t border-border/50">
                            <SectionHeader icon={AtSign} title="账号" />
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                <FieldInput
                                    id="fromAccounts" label="来自这些账号"
                                    placeholder="@elonmusk"
                                    hint="由这些账号发出的推文"
                                    value={params.fromAccounts}
                                    onChange={(e) => update("fromAccounts", (e.target as HTMLInputElement).value)}
                                />
                                <FieldInput
                                    id="toAccounts" label="发给这些账号"
                                    placeholder="@X"
                                    hint="回复给这些账号的推文"
                                    value={params.toAccounts}
                                    onChange={(e) => update("toAccounts", (e.target as HTMLInputElement).value)}
                                />
                                <FieldInput
                                    id="mentionAccounts" label="提及这些账号"
                                    placeholder="@SFBART @Caltrain"
                                    hint="推文中 @提到 了这些账号"
                                    value={params.mentionAccounts}
                                    onChange={(e) => update("mentionAccounts", (e.target as HTMLInputElement).value)}
                                />
                            </div>
                        </div>

                        {/* ── Filters & Engagement 区域 ── */}
                        <div className="space-y-3 pt-3 border-t border-border/50">
                            <SectionHeader icon={Filter} title="筛选条件" />
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                <TriStateFilter
                                    label="回复 (Replies)"
                                    value={params.replyFilter}
                                    onChange={(v) => onChange({ ...params, replyFilter: v })}
                                />
                                <TriStateFilter
                                    label="链接 (Links)"
                                    value={params.linkFilter}
                                    onChange={(v) => onChange({ ...params, linkFilter: v })}
                                />
                            </div>
                        </div>

                        <div className="space-y-3 pt-3 border-t border-border/50">
                            <SectionHeader icon={BarChart3} title="互动量" />
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                <FieldInput
                                    id="minReplies" label="最低回复数"
                                    type="number" min={0}
                                    placeholder="如 280"
                                    hint="至少获得这么多回复"
                                    value={params.minReplies}
                                    onChange={(e) => update("minReplies", (e.target as HTMLInputElement).value)}
                                />
                                <FieldInput
                                    id="minFaves" label="最低点赞数"
                                    type="number" min={0}
                                    placeholder="如 1000"
                                    hint="至少获得这么多点赞"
                                    value={params.minFaves}
                                    onChange={(e) => update("minFaves", (e.target as HTMLInputElement).value)}
                                />
                                <FieldInput
                                    id="minRetweets" label="最低转发数"
                                    type="number" min={0}
                                    placeholder="如 500"
                                    hint="至少获得这么多转发"
                                    value={params.minRetweets}
                                    onChange={(e) => update("minRetweets", (e.target as HTMLInputElement).value)}
                                />
                            </div>
                        </div>

                        {/* ── Dates 区域 ── */}
                        <div className="space-y-3 pt-3 border-t border-border/50">
                            <SectionHeader icon={Calendar} title="时间范围" />
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                <FieldInput
                                    id="since" label="起始日期 (Since)"
                                    type="date"
                                    value={params.since}
                                    onChange={(e) => update("since", (e.target as HTMLInputElement).value)}
                                />
                                <FieldInput
                                    id="until" label="结束日期 (Until)"
                                    type="date"
                                    value={params.until}
                                    onChange={(e) => update("until", (e.target as HTMLInputElement).value)}
                                />
                            </div>
                        </div>

                    </div>
                </div>
            </div>
        </div>
    );
}
