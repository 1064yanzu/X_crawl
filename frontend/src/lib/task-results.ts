export type ResultFilter = "all" | "media" | "replies" | "links";
export type ResultSort = "newest" | "oldest" | "likes" | "engagement";
export type ResultDensity = "comfortable" | "compact";
export type TweetRecord = Record<string, unknown>;

export const RESULT_FILTER_OPTIONS: Array<{ value: ResultFilter; label: string }> = [
    { value: "all", label: "全部结果" },
    { value: "media", label: "带媒体" },
    { value: "replies", label: "带回复" },
    { value: "links", label: "带外链" },
];

export function matchesResultFilter(tweet: TweetRecord, filter: ResultFilter) {
    if (filter === "media") return getTweetMediaCount(tweet) > 0;
    if (filter === "replies") return getTweetReplyCount(tweet) > 0;
    if (filter === "links") return getTweetLinkCount(tweet) > 0;
    return true;
}

export function buildTweetSearchText(tweet: TweetRecord) {
    const author = getTweetAuthor(tweet);
    return [
        typeof tweet.text === "string" ? tweet.text : "",
        typeof author.name === "string" ? author.name : "",
        typeof author.screen_name === "string" ? author.screen_name : "",
        ...getTweetHashtags(tweet),
    ]
        .join(" ")
        .toLowerCase();
}

export function getTweetAuthor(tweet: TweetRecord) {
    const author = tweet.author;
    return author && typeof author === "object" ? (author as TweetRecord) : {};
}

export function getTweetHashtags(tweet: TweetRecord) {
    if (!Array.isArray(tweet.hashtags)) return [] as string[];
    return tweet.hashtags.filter((item): item is string => typeof item === "string");
}

export function getTweetMediaCount(tweet: TweetRecord) {
    return Array.isArray(tweet.media) ? tweet.media.length : 0;
}

export function getTweetReplyCount(tweet: TweetRecord) {
    return Array.isArray(tweet.replies) ? tweet.replies.length : 0;
}

export function getTweetLinkCount(tweet: TweetRecord) {
    return Array.isArray(tweet.urls) ? tweet.urls.length : 0;
}

export function getTweetTimestamp(tweet: TweetRecord) {
    const createdAt = typeof tweet.created_at === "string" ? Date.parse(tweet.created_at) : Number.NaN;
    return Number.isNaN(createdAt) ? 0 : createdAt;
}

export function getTweetMetric(tweet: TweetRecord, key: string) {
    const metrics = tweet.metrics;
    if (!metrics || typeof metrics !== "object") return 0;
    const value = (metrics as Record<string, unknown>)[key];
    return typeof value === "number" ? value : 0;
}

export function getTweetEngagement(tweet: TweetRecord) {
    return getTweetMetric(tweet, "likes") + getTweetMetric(tweet, "retweets") + getTweetMetric(tweet, "replies") + getTweetMetric(tweet, "bookmarks");
}
