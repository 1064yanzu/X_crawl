/**
 * YouTube 视频 URL / ID 解析 —— 与 backend/crawler/youtube/url_parser.py 对齐。
 *
 * 规则说明：
 * - 按换行 / 逗号 / 分号 / 空白拆分原始输入
 * - 命中顺序：纯 11 位 video ID → youtu.be/shorts/embed/v → watch?v=
 * - 返回去重保序的 ids，加上无法解析的原始段（用于在 UI 提示）
 */

const VIDEO_ID = /^[0-9A-Za-z_-]{11}$/;

const URL_PATTERNS: RegExp[] = [
    /youtu\.be\/([0-9A-Za-z_-]{11})(?:[/?&#]|$)/,
    /youtube\.com\/shorts\/([0-9A-Za-z_-]{11})(?:[/?&#]|$)/,
    /youtube\.com\/embed\/([0-9A-Za-z_-]{11})(?:[/?&#]|$)/,
    /youtube\.com\/v\/([0-9A-Za-z_-]{11})(?:[/?&#]|$)/,
    /youtube\.com\/watch\?(?:[^#]*&)?v=([0-9A-Za-z_-]{11})(?:[&#]|$)/,
];

const SPLIT_RE = /[\s,;]+/;

function extractOne(chunk: string): string {
    const text = (chunk ?? "").trim();
    if (!text) return "";
    if (VIDEO_ID.test(text)) return text;
    for (const pattern of URL_PATTERNS) {
        const match = pattern.exec(text);
        if (match) return match[1];
    }
    return "";
}

export interface ParseVideoIdsResult {
    ids: string[];
    invalid: string[];
}

export function parseYouTubeVideoIds(raw: string | string[] | null | undefined): ParseVideoIdsResult {
    if (!raw) return { ids: [], invalid: [] };

    const chunks: string[] = [];
    const pieces = Array.isArray(raw) ? raw : [raw];
    for (const piece of pieces) {
        if (typeof piece !== "string") continue;
        piece.split(SPLIT_RE).forEach((seg) => {
            if (seg.trim()) chunks.push(seg.trim());
        });
    }

    const seen = new Set<string>();
    const ids: string[] = [];
    const invalid: string[] = [];
    for (const chunk of chunks) {
        const vid = extractOne(chunk);
        if (vid) {
            if (!seen.has(vid)) {
                seen.add(vid);
                ids.push(vid);
            }
        } else {
            invalid.push(chunk);
        }
    }
    return { ids, invalid };
}

export function readFileAsText(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result ?? ""));
        reader.onerror = () => reject(reader.error ?? new Error("读取文件失败"));
        reader.readAsText(file);
    });
}

export function isYouTubeVideoId(value: string): boolean {
    return VIDEO_ID.test(value);
}
