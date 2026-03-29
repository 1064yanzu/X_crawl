"use client";
import * as React from "react";
import { api, CrawlerConfig } from "@/services/api";

const DEFAULT_CONFIG: CrawlerConfig = {
    crawler_timeout: 45,
    crawler_page_interval: 5,
    crawler_initial_wait: 3,
    crawler_reply_wait: 4,
    crawler_preview_count: 10,
    crawler_packet_soft_retries: 2,
    crawler_refresh_max_retries: 3,
    crawler_challenge_retry_times: 2,
    crawler_challenge_cooldown: 8,
    crawler_max_concurrent_tasks: 1,
    crawler_cross_platform_concurrent: true,
    scheduler_backend: "memory",
    crawler_adaptive_wait_enabled: true,
    crawler_page_interval_min: 2.5,
    crawler_page_interval_max: 8,
    crawler_interrupt_poll_ms: 300,
    crawler_checkpoint_flush_interval_sec: 4,
    crawler_checkpoint_reply_batch: 3,
    crawler_live_push_interval_ms: 800,
    crawler_auto_throttle_enabled: true,
    crawler_dynamic_concurrency_enabled: true,
    crawler_resource_sample_interval_sec: 2,
    crawler_memory_pressure_warn_pct: 80,
    crawler_memory_pressure_critical_pct: 90,
    crawler_cpu_pressure_warn_pct: 85,
    crawler_cpu_pressure_critical_pct: 95,
    crawler_resource_throttle_max_factor: 3,
    save_raw_responses: true,
    raw_responses_max_pages: 0,
    browser_headless: false,
    browser_background_tabs: false,
    browser_foreground_on_login: true,
    browser_prefer_user_data_dir: true,
    browser_proxy: "",
    browser_load_mode: "normal",
    browser_block_images: false,
    browser_stealth_enabled: true,
    browser_linux_hardening: true,
    browser_pool_auto_close_idle: true,
    crawler_dedup_enabled: true,
    weibo_auto_split_or_keywords: true,
    weibo_time_split_window_days: 7,
    weibo_time_split_max_segments: 600,
    x_auto_time_split_enabled: true,
    x_time_split_trigger_days: 30,
    x_time_split_window_days: 7,
    x_time_split_window_days_unlimited: 7,
    x_time_split_max_segments: 600,
};

export function useCrawlerConfig() {
    const [config, setConfig] = React.useState<CrawlerConfig>(DEFAULT_CONFIG);
    const [original, setOriginal] = React.useState<CrawlerConfig>(DEFAULT_CONFIG);
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);

    React.useEffect(() => {
        api.crawlerConfig.get()
            .then((data) => {
                setConfig(data);
                setOriginal(data);
            })
            .catch(() => undefined)
            .finally(() => setLoading(false));
    }, []);

    const save = React.useCallback(async () => {
        setSaving(true);
        try {
            const updated = await api.crawlerConfig.update(config);
            setConfig(updated);
            setOriginal(updated);
            return updated;
        } finally {
            setSaving(false);
        }
    }, [config]);

    return {
        loading,
        saving,
        config,
        setConfig,
        original,
        isDirty: JSON.stringify(config) !== JSON.stringify(original),
        save,
        reset: () => setConfig(original),
    };
}
