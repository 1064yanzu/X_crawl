export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "/xapi").replace(/\/$/, "");

export type TaskStatus = "pending" | "running" | "done" | "failed" | "paused" | "stopped";
export type CrawlStrategy = "bfs" | "dfs";
export type RiskState = "none" | "challenge" | "rate_limited" | "login_required";
export type QualityState = "complete" | "partial" | "interrupted";

export interface TaskOut {
    task_id: string;
    status: TaskStatus;
    keyword: string;
    product: string;
    max_count: number;
    result_count: number;
    current_page: number;
    created_at: string;
    finished_at?: string | null;
    error?: string | null;
    risk_state: RiskState;
    quality_state?: QualityState;
    runtime_metrics?: Record<string, number>;
    live_metrics?: Record<string, number | string>;
    time_coverage?: Record<string, number | string | null>;
    latest_action?: Record<string, unknown> | null;
    queue_position?: number | null;
    last_event_at?: string | null;
    resumed: boolean;
    // 回复抓取
    fetch_replies: boolean;
    crawl_strategy: CrawlStrategy;
    max_replies_per_tweet: number;
    reply_depth: number;
    replies_fetched: number;
    tweets: Record<string, unknown>[];
    preview_tweets: Record<string, unknown>[];  // 实时预览（最多 N 条）
    crawl_phase: string;  // 爬虫实时阶段描述，如 "等待第 1 页数据包..."
    debug_screenshot?: string | null;
}

export interface CheckpointInfo {
    task_id: string;
    keyword: string;
    product: string;
    tweets_count: number;
    page_fetched: number;
    saved_at: string;
    can_resume: boolean;
}

export interface SearchRequest {
    keyword: string;
    max_count: number;
    product: "Top" | "Latest" | "Photos" | "Videos";
    resume?: boolean;
    task_id?: string;
    // 回复抓取
    fetch_replies?: boolean;
    max_replies_per_tweet?: number;
    reply_depth?: number;
    crawl_strategy?: CrawlStrategy;
}

export interface HealthResponse {
    status: string;
    browser_detected: boolean;
    browser_path: string | null;
    user_data_detected: boolean;
    platform: string;
}

export interface CrawlerConfig {
    crawler_timeout: number;           // 数据包超时（秒）
    crawler_page_interval: number;     // 翻页间隔（秒）
    crawler_initial_wait: number;      // 页面首次加载后等待（秒）
    crawler_reply_wait: number;        // 评论区翻页后等待（秒）
    crawler_preview_count: number;     // 实时预览最大条数
    crawler_packet_soft_retries: number;
    crawler_refresh_max_retries: number;
    crawler_challenge_retry_times: number;
    crawler_challenge_cooldown: number;
    crawler_max_concurrent_tasks: number;
    scheduler_backend?: "memory" | "redis";
    crawler_adaptive_wait_enabled?: boolean;
    crawler_page_interval_min?: number;
    crawler_page_interval_max?: number;
    crawler_interrupt_poll_ms?: number;
    crawler_checkpoint_flush_interval_sec?: number;
    crawler_checkpoint_reply_batch?: number;
    crawler_live_push_interval_ms?: number;
    crawler_auto_throttle_enabled?: boolean;
    crawler_dynamic_concurrency_enabled?: boolean;
    crawler_resource_sample_interval_sec?: number;
    crawler_memory_pressure_warn_pct?: number;
    crawler_memory_pressure_critical_pct?: number;
    crawler_cpu_pressure_warn_pct?: number;
    crawler_cpu_pressure_critical_pct?: number;
    crawler_resource_throttle_max_factor?: number;
    save_raw_responses?: boolean;
    raw_responses_max_pages?: number;
    browser_headless?: boolean;        // 是否无头模式
    browser_proxy?: string;            // 代理配置
    browser_load_mode?: "normal" | "eager";
    browser_block_images?: boolean;
    browser_stealth_enabled?: boolean;
    browser_linux_hardening?: boolean;
    crawler_dedup_enabled?: boolean;   // 跨任务推文去重
}

// 失败评论记录
export interface FailedReplyRecord {
    id: number;
    task_id: string;
    tweet_id: string;
    screen_name: string;
    expected_count: number;
    fetched_count: number;
    error_reason: string;
    status: "pending" | "retrying" | "resolved";
    created_at: string;
    retried_at?: string | null;
}

export interface FailedRepliesResponse {
    task_id: string;
    records: FailedReplyRecord[];
    stats: {
        total: number;
        pending: number;
        retrying: number;
        resolved: number;
    };
}

// 账号池相关类型
export interface AccountOut {
    account_id: string;
    alias: string;
    enabled: boolean;
    is_valid: boolean;
    is_rate_limited: boolean;
    cookie_count: number;
    cookie_domains: string[];
    use_count: number;
    fail_count: number;
    added_at: number;
    last_used_at: number;
    last_validated_at: number;
    rate_reset_at: number;
}

export interface AddAccountRequest {
    alias: string;
    cookies: Array<{ name: string; value: string; domain?: string }>;
    raw_cookie_string?: string;
}

export interface UpdateAccountRequest {
    alias?: string;
    enabled?: boolean;
}

export interface IntervalSuggestion {
    active_account_count: number;
    total_account_count: number;
    search_interval_min: number;
    search_interval_max: number;
    search_safe_interval: number;
    tweet_detail_interval_min: number;
    tweet_detail_interval_max: number;
    tweet_detail_safe_interval: number;
    note: string;
}
    name: string;
    value_masked: string;
    domain: string;
}

export interface CookiesResponse {
    count: number;
    cookies: CookieItem[];
}

export interface CaptureResponse {
    captured: number;
    message: string;
}

// 浏览器管理相关
export interface BrowserInfo {
    id: string;
    name: string;
    engine: string;        // "chromium" | "firefox" | "other"
    compatible: boolean;
    path: string;
    user_data_path: string | null;
    selected: boolean;
}

export interface BrowserListResponse {
    platform: string;
    count: number;
    selected_id: string;
    browsers: BrowserInfo[];
}

export interface BrowserSelectResponse {
    message: string;
    browser_id: string;
    browser_name: string | null;
    restart_required: boolean;
}

// 原始响应存储相关
export interface StorageTask {
    task_id: string;
    page_count: number;
    total_bytes: number;
    latest_at: string;
}

export interface StorageInfo {
    save_enabled: boolean;
    max_pages_per_task?: number;
    storage_dir: string;
    tasks: StorageTask[];
}

/**
 * Common fetch utility that handles JSON parsing and error throwing.
 */
async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;

    const headers = {
        "Content-Type": "application/json",
        ...options?.headers,
    };

    const response = await fetch(url, { ...options, headers });

    if (!response.ok) {
        let errorDetail = response.statusText;
        try {
            const errorData = await response.json();
            if (errorData.detail) errorDetail = errorData.detail;
            else if (errorData.message) errorDetail = errorData.message;
        } catch {
            // Ignore JSON parse err
        }
        throw new Error(`API Error: ${response.status} - ${errorDetail}`);
    }

    return response.json();
}

/**
 * 下载文件（触发浏览器 Save Dialog）
 */
async function downloadBlob(url: string, fallbackFilename: string): Promise<void> {
    try {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`下载失败: ${resp.status}`);

        // 从 Content-Disposition 提取服务器端生成的文件名
        const disposition = resp.headers.get("Content-Disposition") || "";
        let filename = fallbackFilename;
        // 优先匹配 filename*=UTF-8'' 编码格式（支持中文）
        const utf8Match = disposition.match(/filename\*=UTF-8''(.+)/i);
        if (utf8Match) {
            filename = decodeURIComponent(utf8Match[1]);
        } else {
            // 降级匹配 filename="xxx"
            const plainMatch = disposition.match(/filename="?([^";\n]+)"?/i);
            if (plainMatch) filename = plainMatch[1].trim();
        }

        const blob = await resp.blob();
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
    } catch (err) {
        console.error("导出下载失败:", err);
        throw new Error(`导出下载失败: ${err instanceof Error ? err.message : String(err)}`);
    }
}

export const api = {
    health: {
        check: () => fetchApi<HealthResponse>("/health"),
    },
    crawlerConfig: {
        get: () => fetchApi<CrawlerConfig>("/api/v1/crawler-config"),
        update: (config: CrawlerConfig) =>
            fetchApi<CrawlerConfig>("/api/v1/crawler-config", {
                method: "PUT",
                body: JSON.stringify(config),
            }),
    },
    search: {
        create: (data: SearchRequest) =>
            fetchApi<TaskOut>("/api/v1/search", {
                method: "POST",
                body: JSON.stringify(data),
            }),
        get: (taskId: string, includeTweets = true) =>
            fetchApi<TaskOut>(`/api/v1/search/${taskId}?include_tweets=${includeTweets ? "true" : "false"}`),
    },
    tasks: {
        list: (includePayload = false) =>
            fetchApi<TaskOut[]>(`/api/v1/tasks?include_payload=${includePayload ? "true" : "false"}`),
        streamUrl: (taskId: string) =>
            `${API_BASE_URL}/api/v1/tasks/${taskId}/stream`,
        delete: (taskId: string) =>
            fetchApi<{ message: string }>(`/api/v1/tasks/${taskId}`, { method: "DELETE" }),
        pause: (taskId: string) =>
            fetchApi<{ message: string; status: string }>(`/api/v1/tasks/${taskId}/pause`, { method: "POST" }),
        resume: (taskId: string) =>
            fetchApi<{ message: string; status: string }>(`/api/v1/tasks/${taskId}/resume`, { method: "POST" }),
        stop: (taskId: string) =>
            fetchApi<{ message: string; status: string }>(`/api/v1/tasks/${taskId}/stop`, { method: "POST" }),
    },
    checkpoints: {
        list: () => fetchApi<CheckpointInfo[]>("/api/v1/checkpoints"),
        delete: (taskId: string) =>
            fetchApi<{ message: string }>(`/api/v1/checkpoints/${taskId}`, { method: "DELETE" }),
    },
    cookies: {
        list: () => fetchApi<CookiesResponse>("/api/v1/cookies"),
        save: (cookies: Array<{ name: string; value: string; domain?: string }>) =>
            fetchApi<CookiesResponse>("/api/v1/cookies", {
                method: "POST",
                body: JSON.stringify({ cookies }),
            }),
        saveRaw: (rawString: string) =>
            fetchApi<CookiesResponse>("/api/v1/cookies", {
                method: "POST",
                body: JSON.stringify({ raw_string: rawString }),
            }),
        clear: () =>
            fetchApi<{ message: string }>("/api/v1/cookies", { method: "DELETE" }),
        capture: () =>
            fetchApi<CaptureResponse>("/api/v1/cookies/capture", { method: "POST" }),
        exportJson: async () => {
            const url = `${API_BASE_URL}/api/v1/cookies/export`;
            await downloadBlob(url, "xcrawl-cookies.json");
        },
        exportString: async () => {
            const url = `${API_BASE_URL}/api/v1/cookies/export/string`;
            await downloadBlob(url, "xcrawl-cookies.txt");
        },
    },
    export: {
        downloadCsv: async (taskId: string) => {
            const url = `${API_BASE_URL}/api/v1/export/${taskId}/csv`;
            await downloadBlob(url, `xcrawl_${taskId.substring(0, 8)}.csv`);
        },
        downloadExcel: async (taskId: string) => {
            const url = `${API_BASE_URL}/api/v1/export/${taskId}/excel`;
            await downloadBlob(url, `xcrawl_${taskId.substring(0, 8)}.xlsx`);
        },
    },
    failedReplies: {
        list: (taskId: string) =>
            fetchApi<FailedRepliesResponse>(`/api/v1/failed-replies/${taskId}`),
        retry: (taskId: string) =>
            fetchApi<{ message: string; retried: number }>(`/api/v1/failed-replies/${taskId}/retry`, {
                method: "POST",
            }),
        exportCsv: async (taskId: string) => {
            const url = `${API_BASE_URL}/api/v1/failed-replies/${taskId}/export`;
            await downloadBlob(url, `failed_replies_${taskId.substring(0, 8)}.csv`);
        },
    },
    browsers: {
        list: () =>
            fetchApi<BrowserListResponse>("/api/v1/browsers"),
        select: (browserId: string) =>
            fetchApi<BrowserSelectResponse>("/api/v1/browsers/select", {
                method: "PUT",
                body: JSON.stringify({ browser_id: browserId }),
            }),
        getSelected: () =>
            fetchApi<BrowserInfo>("/api/v1/browsers/selected"),
    },
    rawResponses: {
        list: () =>
            fetchApi<StorageInfo>("/api/v1/raw-responses/"),
        deleteTask: (taskId: string) =>
            fetchApi<{ task_id: string; deleted_files: number }>(`/api/v1/raw-responses/${taskId}`, { method: "DELETE" }),
        deleteAll: () =>
            fetchApi<{ deleted_tasks: number; deleted_files: number }>("/api/v1/raw-responses/all", { method: "DELETE" }),
    },
    accounts: {
        list: () =>
            fetchApi<AccountOut[]>("/api/v1/accounts"),
        add: (req: AddAccountRequest) =>
            fetchApi<AccountOut>("/api/v1/accounts", {
                method: "POST",
                body: JSON.stringify(req),
            }),
        update: (accountId: string, req: UpdateAccountRequest) =>
            fetchApi<AccountOut>(`/api/v1/accounts/${accountId}`, {
                method: "PUT",
                body: JSON.stringify(req),
            }),
        delete: (accountId: string) =>
            fetchApi<{ message: string }>(`/api/v1/accounts/${accountId}`, { method: "DELETE" }),
        validate: (accountId: string) =>
            fetchApi<AccountOut>(`/api/v1/accounts/${accountId}/validate`, { method: "POST" }),
        intervalSuggestion: () =>
            fetchApi<IntervalSuggestion>("/api/v1/accounts/interval-suggestion"),
    },
};
