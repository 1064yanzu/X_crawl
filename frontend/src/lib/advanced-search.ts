export interface AdvancedSearchParams {
    allWords: string;
    exactPhrase: string;
    anyWords: string;
    noneWords: string;
    hashtags: string;
    lang: string;
    fromAccounts: string;
    toAccounts: string;
    mentionAccounts: string;
    replyFilter: "off" | "include" | "only";
    linkFilter: "off" | "include" | "only";
    minReplies: string;
    minFaves: string;
    minRetweets: string;
    since: string;
    until: string;
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

export function buildAdvancedQuery(params: AdvancedSearchParams): string {
    const parts: string[] = [];

    if (params.allWords.trim()) {
        parts.push(params.allWords.trim());
    }

    if (params.exactPhrase.trim()) {
        parts.push(`"${params.exactPhrase.trim()}"`);
    }

    if (params.anyWords.trim()) {
        const words = params.anyWords.trim().split(/\s+/).filter(Boolean);
        if (words.length > 1) {
            parts.push(`(${words.join(" OR ")})`);
        } else if (words.length === 1) {
            parts.push(words[0]);
        }
    }

    if (params.noneWords.trim()) {
        const words = params.noneWords.trim().split(/\s+/).filter(Boolean);
        for (const word of words) {
            parts.push(`-${word}`);
        }
    }

    if (params.hashtags.trim()) {
        const tags = params.hashtags.trim().split(/\s+/).filter(Boolean);
        for (const tag of tags) {
            parts.push(tag.startsWith("#") ? tag : `#${tag}`);
        }
    }

    if (params.lang) {
        parts.push(`lang:${params.lang}`);
    }

    if (params.fromAccounts.trim()) {
        const accounts = params.fromAccounts.trim().split(/[\s,]+/).filter(Boolean);
        const fromParts = accounts.map((account) => `from:${account.replace(/^@/, "")}`);
        if (fromParts.length > 1) {
            parts.push(`(${fromParts.join(" OR ")})`);
        } else if (fromParts.length === 1) {
            parts.push(fromParts[0]);
        }
    }

    if (params.toAccounts.trim()) {
        const accounts = params.toAccounts.trim().split(/[\s,]+/).filter(Boolean);
        const toParts = accounts.map((account) => `to:${account.replace(/^@/, "")}`);
        if (toParts.length > 1) {
            parts.push(`(${toParts.join(" OR ")})`);
        } else if (toParts.length === 1) {
            parts.push(toParts[0]);
        }
    }

    if (params.mentionAccounts.trim()) {
        const accounts = params.mentionAccounts.trim().split(/[\s,]+/).filter(Boolean);
        for (const account of accounts) {
            parts.push(account.startsWith("@") ? account : `@${account}`);
        }
    }

    if (params.replyFilter === "only") {
        parts.push("filter:replies");
    }

    if (params.linkFilter === "only") {
        parts.push("filter:links");
    }

    if (params.minReplies && Number(params.minReplies) > 0) {
        parts.push(`min_replies:${params.minReplies}`);
    }
    if (params.minFaves && Number(params.minFaves) > 0) {
        parts.push(`min_faves:${params.minFaves}`);
    }
    if (params.minRetweets && Number(params.minRetweets) > 0) {
        parts.push(`min_retweets:${params.minRetweets}`);
    }

    if (params.since) {
        parts.push(`since:${params.since}`);
    }
    if (params.until) {
        parts.push(`until:${params.until}`);
    }

    return parts.join(" ");
}

export function hasActiveFilters(params: AdvancedSearchParams): boolean {
    return Boolean(
        params.allWords || params.exactPhrase || params.anyWords ||
        params.noneWords || params.hashtags || params.lang ||
        params.fromAccounts || params.toAccounts || params.mentionAccounts ||
        params.replyFilter !== "off" || params.linkFilter !== "off" ||
        params.minReplies || params.minFaves || params.minRetweets ||
        params.since || params.until,
    );
}
