export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "/xapi").replace(/\/$/, "");

export type TaskStatus = "pending" | "running" | "done" | "failed" | "paused" | "stopped";
export type Platform = "x" | "weibo";
export type CrawlStrategy = "bfs" | "dfs";
export type TaskKind = "search" | "comment_backfill";
export type RiskState = "none" | "challenge" | "rate_limited" | "login_required" | "search_blocked";
export type QualityState = "complete" | "partial" | "interrupted";

export interface SegmentProgress {
    enabled: boolean;
    total_segments: number;
    completed_segments: number;
    current_segment_index: number;
    current_since?: string | null;
    current_until?: string | null;
}

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
    segment_progress?: SegmentProgress;
    // 回复抓取
    fetch_replies: boolean;
    crawl_strategy: CrawlStrategy;
    max_replies_per_tweet: number;
    reply_depth: number;
    replies_fetched: number;
    task_kind?: TaskKind;
    source_file_name?: string | null;
    source_task_id?: string | null;
    queue_id?: string | null;
    queue_name?: string | null;
    queue_order?: number | null;
    queue_total?: number | null;
    comment_backfill_progress?: {
        total_posts: number;
        eligible_posts: number;
        processed_posts: number;
        skipped_posts: number;
        succeeded_posts: number;
        failed_posts: number;
    };
    tweets: Record<string, unknown>[];
    preview_tweets: Record<string, unknown>[];  // 实时预览（最多 N 条）
    crawl_phase: string;  // 爬虫实时阶段描述，如 "等待第 1 页数据包..."
    platform?: Platform;
    start_date?: string | null;
    end_date?: string | null;
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
    platform?: Platform;
    start_date?: string;
    end_date?: string;
}

export interface TaskQueueItemRequest {
    keyword: string;
    max_count: number;
    product: "Top" | "Latest" | "Photos" | "Videos";
    fetch_replies?: boolean;
    max_replies_per_tweet?: number;
    reply_depth?: number;
    crawl_strategy?: CrawlStrategy;
    platform?: Platform;
    start_date?: string;
    end_date?: string;
}

export interface TaskQueueCreateRequest {
    name?: string;
    tasks: TaskQueueItemRequest[];
}

export interface TaskQueueOut {
    queue_id: string;
    name: string;
    status: "running" | "paused" | "completed";
    created_at: string;
    started_at?: string | null;
    finished_at?: string | null;
    current_task_id?: string | null;
    total_tasks: number;
    completed_tasks: number;
    running_tasks: number;
    pending_tasks: number;
    failed_tasks: number;
    stopped_tasks: number;
    tasks: TaskOut[];
}

export interface CommentBackfillAnalyzeResponse {
    file_name: string;
    platform: Platform;
    total_rows: number;
    original_post_rows: number;
    unique_post_count: number;
    eligible_posts: number;
    skipped_non_post_rows: number;
    skipped_zero_comment_posts: number;
    skipped_invalid_posts: number;
    deduplicated_posts: number;
    has_platform_column: boolean;
    detected_platform?: Platform | null;
}

export interface CommentBackfillImportResponse {
    task: TaskOut;
    summary: CommentBackfillAnalyzeResponse;
}

export interface CommentBackfillTaskSourceSummary {
    source_task_id: string;
    source_keyword: string;
    platform: Platform;
    task_status: string;
    result_count: number;
    unique_post_count: number;
    eligible_posts: number;
    skipped_zero_comment_posts: number;
    skipped_invalid_posts: number;
    skipped_existing_comment_posts: number;
    deduplicated_posts: number;
    status: "created" | "skipped";
    reason?: string | null;
    created_task_id?: string | null;
}

export interface CommentBackfillFromTasksResponse {
    created_count: number;
    queued: boolean;
    queue?: TaskQueueOut | null;
    tasks: TaskOut[];
    sources: CommentBackfillTaskSourceSummary[];
}

// 批量导入
export interface BatchImportTask {
    keyword: string;
    max_count: number;
    product: "Top" | "Latest" | "Photos" | "Videos";
    platform: Platform;
    fetch_replies: boolean;
    reply_depth: number;
    max_replies_per_tweet: number;
    crawl_strategy: CrawlStrategy;
    start_date?: string | null;
    end_date?: string | null;
}

export interface BatchImportParseResult {
    total: number;
    tasks: BatchImportTask[];
    errors: string[];
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
    crawler_cross_platform_concurrent?: boolean;
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
    browser_background_tabs?: boolean; // 是否后台创建新标签页
    browser_foreground_on_login?: boolean; // 登录/风控时是否自动前台唤起浏览器
    browser_prefer_user_data_dir?: boolean; // 启动新浏览器时优先复用真实用户目录
    browser_proxy?: string;            // 代理配置
    browser_load_mode?: "normal" | "eager";
    browser_block_images?: boolean;
    browser_stealth_enabled?: boolean;
    browser_linux_hardening?: boolean;
    crawler_dedup_enabled?: boolean;   // 跨任务推文去重
    weibo_auto_split_or_keywords?: boolean;
    x_auto_time_split_enabled?: boolean;
    x_time_split_trigger_days?: number;
    x_time_split_window_days?: number;
    x_time_split_window_days_unlimited?: number;
    x_time_split_max_segments?: number;
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

// 微博账号池相关类型
export interface WeiboAccountOut {
    account_id: string;
    alias: string;
    enabled: boolean;
    is_valid: boolean;
    is_rate_limited: boolean;
    cookie_count: number;
    use_count: number;
    fail_count: number;
    added_at: number;
    last_used_at: number;
    last_validated_at: number;
    rate_reset_at: number;
}

export interface AddWeiboAccountRequest {
    alias: string;
    cookies?: Array<Record<string, string>>;
    raw_cookie_string?: string;
}

export interface UpdateWeiboAccountRequest {
    alias?: string;
    enabled?: boolean;
}

export interface CookieItem {
    name: string;
    value_masked: string;
    domain: string;
    category: "auth" | "session" | "other";
    is_critical: boolean;
}

export interface CookieAccount {
    user_id: string;
    cookie_count: number;
    has_login: boolean;
    cookies: CookieItem[];
}

export interface CookiesResponse {
    count: number;
    has_login: boolean;
    accounts: CookieAccount[];
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
    session_mode: string;
    effective_user_data_path: string | null;
    crawler_profile_path: string;
    crawler_profile_exists: boolean;
    crawler_profile_initialized: boolean;
    browser_alive: boolean;
    headless: boolean;
    last_login_check_at: string | null;
    last_login_success_at: string | null;
    last_login_failure_reason: string | null;
    last_page_state: string | null;
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

async function fetchFormApi<T>(endpoint: string, formData: FormData): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    const response = await fetch(url, {
        method: "POST",
        body: formData,
    });

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

/**
 * POST 下载文件（用于需要传 body 的批量导出场景）
 */
async function downloadPostBlob(endpoint: string, body: unknown, fallbackFilename: string): Promise<void> {
    try {
        const url = `${API_BASE_URL}${endpoint}`;
        const resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            let detail = resp.statusText;
            try {
                const errData = await resp.json();
                if (errData.detail) detail = errData.detail;
            } catch { /* ignore */ }
            throw new Error(`导出失败: ${resp.status} - ${detail}`);
        }

        const disposition = resp.headers.get("Content-Disposition") || "";
        let filename = fallbackFilename;
        const utf8Match = disposition.match(/filename\*=UTF-8''(.+)/i);
        if (utf8Match) {
            filename = decodeURIComponent(utf8Match[1]);
        } else {
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
        console.error("批量导出下载失败:", err);
        throw new Error(`批量导出下载失败: ${err instanceof Error ? err.message : String(err)}`);
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
    commentBackfill: {
        analyze: (file: File, platform: Platform) => {
            const formData = new FormData();
            formData.append("file", file);
            formData.append("platform", platform);
            return fetchFormApi<CommentBackfillAnalyzeResponse>("/api/v1/comment-backfill/analyze", formData);
        },
        import: (params: {
            file: File;
            platform: Platform;
            replyDepth: number;
            maxRepliesPerTweet: number;
        }) => {
            const formData = new FormData();
            formData.append("file", params.file);
            formData.append("platform", params.platform);
            formData.append("reply_depth", String(params.replyDepth));
            formData.append("max_replies_per_tweet", String(params.maxRepliesPerTweet));
            return fetchFormApi<CommentBackfillImportResponse>("/api/v1/comment-backfill/import", formData);
        },
        fromTasks: (params: {
            taskIds: string[];
            replyDepth?: number;
            maxRepliesPerTweet?: number;
            queueName?: string;
        }) =>
            fetchApi<CommentBackfillFromTasksResponse>("/api/v1/comment-backfill/from-tasks", {
                method: "POST",
                body: JSON.stringify({
                    task_ids: params.taskIds,
                    reply_depth: params.replyDepth ?? 2,
                    max_replies_per_tweet: params.maxRepliesPerTweet ?? 0,
                    queue_name: params.queueName,
                }),
            }),
    },
    taskQueues: {
        create: (data: TaskQueueCreateRequest) =>
            fetchApi<TaskQueueOut>("/api/v1/task-queues", {
                method: "POST",
                body: JSON.stringify(data),
            }),
        list: () => fetchApi<TaskQueueOut[]>("/api/v1/task-queues"),
        get: (queueId: string) => fetchApi<TaskQueueOut>(`/api/v1/task-queues/${queueId}`),
        resume: (queueId: string) =>
            fetchApi<{ message: string; resumed: string[]; skipped: string[]; already_running: string[] }>(
                `/api/v1/task-queues/${queueId}/resume`,
                { method: "POST" },
            ),
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
        resumeAll: () =>
            fetchApi<{
                message: string;
                resumed: string[];
                already_running: string[];
                skipped: string[];
                failed: string[];
            }>("/api/v1/tasks/resume-all", { method: "POST" }),
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
        deleteSingle: (cookieName: string, domain?: string) => {
            const params = domain ? `?domain=${encodeURIComponent(domain)}` : "";
            return fetchApi<CookiesResponse>(`/api/v1/cookies/${encodeURIComponent(cookieName)}${params}`, {
                method: "DELETE",
            });
        },
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
        downloadCsv: async (taskId: string, deduplicate = false) => {
            const params = new URLSearchParams();
            if (deduplicate) params.set("deduplicate", "true");
            const url = `${API_BASE_URL}/api/v1/export/${taskId}/csv${params.size > 0 ? `?${params.toString()}` : ""}`;
            await downloadBlob(url, `xcrawl_${taskId.substring(0, 8)}.csv`);
        },
        downloadExcel: async (taskId: string, deduplicate = false) => {
            const params = new URLSearchParams();
            if (deduplicate) params.set("deduplicate", "true");
            const url = `${API_BASE_URL}/api/v1/export/${taskId}/excel${params.size > 0 ? `?${params.toString()}` : ""}`;
            await downloadBlob(url, `xcrawl_${taskId.substring(0, 8)}.xlsx`);
        },
        batchDownloadCsv: async (taskIds: string[], deduplicate = false) => {
            await downloadPostBlob(
                "/api/v1/export/batch/csv",
                { task_ids: taskIds, merge_mode: "single", deduplicate },
                `batch_${taskIds.length}tasks.csv`,
            );
        },
        batchDownloadExcel: async (taskIds: string[], mergeMode: "single" | "per_task" = "per_task", deduplicate = false) => {
            await downloadPostBlob(
                "/api/v1/export/batch/excel",
                { task_ids: taskIds, merge_mode: mergeMode, deduplicate },
                `batch_${taskIds.length}tasks.xlsx`,
            );
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
    batchImport: {
        parseFile: (params: {
            file: File;
            defaultPlatform?: Platform;
            defaultProduct?: string;
            defaultMaxCount?: number;
            defaultFetchReplies?: boolean;
        }) => {
            const formData = new FormData();
            formData.append("file", params.file);
            if (params.defaultPlatform) formData.append("default_platform", params.defaultPlatform);
            if (params.defaultProduct) formData.append("default_product", params.defaultProduct);
            if (params.defaultMaxCount !== undefined) formData.append("default_max_count", String(params.defaultMaxCount));
            if (params.defaultFetchReplies !== undefined) formData.append("default_fetch_replies", String(params.defaultFetchReplies));
            return fetchFormApi<BatchImportParseResult>("/api/v1/batch-import/parse", formData);
        },
    },
    weiboCookies: {
        list: () =>
            fetchApi<{
                cookies: { name: string; masked: string }[];
                has_login: boolean;
                count: number;
            }>("/api/v1/weibo-cookies"),
        save: (data: { cookies?: Record<string, string>[]; raw_string?: string }) =>
            fetchApi<{ saved: number; has_login: boolean }>("/api/v1/weibo-cookies", {
                method: "POST",
                body: JSON.stringify(data),
            }),
        clear: () =>
            fetchApi<{ message: string }>("/api/v1/weibo-cookies", { method: "DELETE" }),
        capture: () =>
            fetchApi<{
                captured: number;
                has_login: boolean;
                message?: string;
            }>("/api/v1/weibo-cookies/capture", { method: "POST" }),
    },
    weiboAccounts: {
        list: () =>
            fetchApi<WeiboAccountOut[]>("/api/v1/weibo-accounts"),
        add: (req: AddWeiboAccountRequest) =>
            fetchApi<WeiboAccountOut>("/api/v1/weibo-accounts", {
                method: "POST",
                body: JSON.stringify(req),
            }),
        update: (accountId: string, req: UpdateWeiboAccountRequest) =>
            fetchApi<WeiboAccountOut>(`/api/v1/weibo-accounts/${accountId}`, {
                method: "PUT",
                body: JSON.stringify(req),
            }),
        delete: (accountId: string) =>
            fetchApi<{ message: string }>(`/api/v1/weibo-accounts/${accountId}`, { method: "DELETE" }),
        validate: (accountId: string) =>
            fetchApi<WeiboAccountOut>(`/api/v1/weibo-accounts/${accountId}/validate`, { method: "POST" }),
    },
};
