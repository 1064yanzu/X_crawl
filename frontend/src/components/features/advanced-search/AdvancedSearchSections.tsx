import * as React from "react";
import { AtSign, BarChart3, Calendar, Filter, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { type AdvancedSearchParams } from "@/lib/advanced-search";

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

type UpdateFn = (key: keyof AdvancedSearchParams, value: string) => void;
type TriStateValue = "off" | "include" | "only";

function SectionHeader({ icon: Icon, title }: { icon: React.ElementType; title: string }) {
    return (
        <div className="flex items-center gap-2 pb-1">
            <Icon className="h-3.5 w-3.5 text-primary/70" />
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</span>
        </div>
    );
}

function FieldInput({
    label,
    hint,
    id,
    ...inputProps
}: { label: string; hint?: string; id: string } & React.InputHTMLAttributes<HTMLInputElement>) {
    return (
        <div className="space-y-1.5">
            <label htmlFor={id} className="block text-xs font-medium text-foreground/80">{label}</label>
            <Input id={id} className="h-9" {...inputProps} />
            {hint ? <p className="text-[11px] leading-tight text-muted-foreground/70">{hint}</p> : null}
        </div>
    );
}

function TriStateFilter({
    label,
    value,
    onChange,
}: {
    label: string;
    value: TriStateValue;
    onChange: (value: TriStateValue) => void;
}) {
    const options = [
        { value: "off" as const, label: "关闭" },
        { value: "include" as const, label: "包含" },
        { value: "only" as const, label: "仅显示" },
    ];

    return (
        <div className="space-y-1.5">
            <span className="text-xs font-medium text-foreground/80">{label}</span>
            <div className="flex gap-1 rounded-lg border border-border bg-muted/50 p-0.5">
                {options.map((option) => (
                    <button
                        key={option.value}
                        type="button"
                        onClick={() => onChange(option.value)}
                        className={`flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition-all duration-200 ${
                            value === option.value
                                ? "border border-border bg-background text-foreground shadow-sm"
                                : "text-muted-foreground hover:text-foreground"
                        }`}
                    >
                        {option.label}
                    </button>
                ))}
            </div>
        </div>
    );
}

export function WordsSection({ params, update }: { params: AdvancedSearchParams; update: UpdateFn }) {
    return (
        <div className="space-y-3">
            <SectionHeader icon={Search} title="关键词" />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <FieldInput id="allWords" label="包含这些词" placeholder="如 electric bus" hint="这些词都需要出现" value={params.allWords} onChange={(event) => update("allWords", event.target.value)} />
                <FieldInput id="exactPhrase" label="精确短语" placeholder={'如 "new energy"'} hint="按完整短语精确匹配" value={params.exactPhrase} onChange={(event) => update("exactPhrase", event.target.value)} />
                <FieldInput id="anyWords" label="任意这些词" placeholder="ai robot llm" hint="多个词会自动用 OR 拼接" value={params.anyWords} onChange={(event) => update("anyWords", event.target.value)} />
                <FieldInput id="noneWords" label="排除这些词" placeholder="job hiring" hint="这些词将被排除" value={params.noneWords} onChange={(event) => update("noneWords", event.target.value)} />
                <FieldInput id="hashtags" label="包含话题" placeholder="#OpenAI #AI" hint="支持多个 hashtag" value={params.hashtags} onChange={(event) => update("hashtags", event.target.value)} />
                <div className="space-y-1.5">
                    <label htmlFor="lang" className="block text-xs font-medium text-foreground/80">语言</label>
                    <select id="lang" value={params.lang} onChange={(event) => update("lang", event.target.value)} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
                        {LANGUAGES.map((language) => (
                            <option key={language.value} value={language.value}>{language.label}</option>
                        ))}
                    </select>
                </div>
            </div>
        </div>
    );
}

export function AccountsSection({ params, update }: { params: AdvancedSearchParams; update: UpdateFn }) {
    return (
        <div className="space-y-3 border-t border-border pt-3">
            <SectionHeader icon={AtSign} title="账号" />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <FieldInput id="fromAccounts" label="来自这些账号" placeholder="@elonmusk" hint="由这些账号发出的推文" value={params.fromAccounts} onChange={(event) => update("fromAccounts", event.target.value)} />
                <FieldInput id="toAccounts" label="发给这些账号" placeholder="@X" hint="回复给这些账号的推文" value={params.toAccounts} onChange={(event) => update("toAccounts", event.target.value)} />
                <FieldInput id="mentionAccounts" label="提及这些账号" placeholder="@SFBART @Caltrain" hint="推文中 @提到 了这些账号" value={params.mentionAccounts} onChange={(event) => update("mentionAccounts", event.target.value)} />
            </div>
        </div>
    );
}

export function FilterSection({
    params,
    onReplyChange,
    onLinkChange,
}: {
    params: AdvancedSearchParams;
    onReplyChange: (value: TriStateValue) => void;
    onLinkChange: (value: TriStateValue) => void;
}) {
    return (
        <div className="space-y-3 border-t border-border pt-3">
            <SectionHeader icon={Filter} title="筛选条件" />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <TriStateFilter label="回复 (Replies)" value={params.replyFilter} onChange={onReplyChange} />
                <TriStateFilter label="链接 (Links)" value={params.linkFilter} onChange={onLinkChange} />
            </div>
        </div>
    );
}

export function EngagementSection({ params, update }: { params: AdvancedSearchParams; update: UpdateFn }) {
    return (
        <div className="space-y-3 border-t border-border pt-3">
            <SectionHeader icon={BarChart3} title="互动量" />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <FieldInput id="minReplies" label="最低回复数" type="number" min={0} placeholder="如 280" hint="至少获得这么多回复" value={params.minReplies} onChange={(event) => update("minReplies", event.target.value)} />
                <FieldInput id="minFaves" label="最低点赞数" type="number" min={0} placeholder="如 1000" hint="至少获得这么多点赞" value={params.minFaves} onChange={(event) => update("minFaves", event.target.value)} />
                <FieldInput id="minRetweets" label="最低转发数" type="number" min={0} placeholder="如 500" hint="至少获得这么多转发" value={params.minRetweets} onChange={(event) => update("minRetweets", event.target.value)} />
            </div>
        </div>
    );
}

export function DatesSection({ params, update }: { params: AdvancedSearchParams; update: UpdateFn }) {
    return (
        <div className="space-y-3 border-t border-border pt-3">
            <SectionHeader icon={Calendar} title="时间范围" />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <FieldInput id="since" label="起始日期 (Since)" type="date" value={params.since} onChange={(event) => update("since", event.target.value)} />
                <FieldInput id="until" label="结束日期 (Until)" type="date" value={params.until} onChange={(event) => update("until", event.target.value)} />
            </div>
        </div>
    );
}
