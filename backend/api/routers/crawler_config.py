"""
爬虫参数配置路由（v2 - 设置持久化，用户配置优先于 .env）

GET  /api/v1/crawler-config        获取当前爬虫配置
PUT  /api/v1/crawler-config        更新爬虫配置（持久化到数据库，重启后仍生效）
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional
from config import settings
from api.services.settings_db import set_settings_batch
from api.services.task_scheduler import scheduler

router = APIRouter(prefix="/api/v1/crawler-config", tags=["爬虫配置"])


class CrawlerConfig(BaseModel):
    """爬虫运行参数（含持久化字段）"""
    # 爬虫速率参数
    crawler_timeout: float = Field(description="等待数据包超时时间（秒）", ge=5.0, le=120.0)
    crawler_page_interval: float = Field(description="翻页操作间隔（秒）", ge=1.0, le=60.0)
    crawler_initial_wait: float = Field(description="页面首次加载后额外等待（秒）", ge=0.0, le=30.0)
    crawler_reply_wait: float = Field(description="评论区每次翻页后额外等待（秒）", ge=0.0, le=30.0)
    crawler_preview_count: int = Field(description="实时预览最大展示条数", ge=1, le=50)
    crawler_packet_soft_retries: int = Field(description="单页数据包软重试次数", ge=0, le=8)
    crawler_refresh_max_retries: int = Field(description="硬刷新最大重试次数", ge=1, le=10)
    crawler_challenge_retry_times: int = Field(description="挑战页自动重试次数", ge=0, le=8)
    crawler_challenge_cooldown: float = Field(description="挑战页重试冷却时间（秒）", ge=1.0, le=60.0)
    crawler_cloudflare_wait_seconds: float = Field(default=60.0, description="Cloudflare 验证等待时长（秒）", ge=10.0, le=300.0)
    crawler_max_concurrent_tasks: int = Field(description="并发运行任务上限", ge=1, le=5)
    crawler_cross_platform_concurrent: bool = Field(default=True, description="是否允许 X 和微博任务跨平台并发执行")
    scheduler_backend: str = Field(default="memory", description="调度后端：memory/redis")
    crawler_adaptive_wait_enabled: bool = Field(default=True, description="是否启用自适应等待")
    crawler_page_interval_min: float = Field(default=2.5, ge=0.5, le=120.0, description="翻页间隔下限（秒）")
    crawler_page_interval_max: float = Field(default=8.0, ge=0.5, le=180.0, description="翻页间隔上限（秒）")
    crawler_interrupt_poll_ms: int = Field(default=300, ge=50, le=3000, description="中断轮询粒度（毫秒）")
    crawler_checkpoint_flush_interval_sec: float = Field(
        default=4.0, ge=0.2, le=60.0, description="DFS 回复阶段检查点刷新间隔（秒）"
    )
    crawler_checkpoint_reply_batch: int = Field(
        default=3, ge=1, le=200, description="DFS 回复阶段每累计多少条触发一次检查点刷新"
    )
    crawler_live_push_interval_ms: int = Field(
        default=800, ge=200, le=5000, description="SSE 实时推送间隔（毫秒）"
    )
    crawler_active_task_watchdog_enabled: bool = Field(default=True, description="是否启用活跃任务卡死巡检与自动重排")
    crawler_active_task_stale_timeout_sec: float = Field(
        default=900.0,
        ge=60.0,
        le=7200.0,
        description="活跃任务超过多久无事件视为卡死（秒）",
    )
    crawler_active_task_watchdog_interval_sec: float = Field(
        default=30.0,
        ge=5.0,
        le=600.0,
        description="活跃任务巡检执行间隔（秒）",
    )
    crawler_auto_throttle_enabled: bool = Field(default=True, description="是否启用资源压力自动节流")
    crawler_dynamic_concurrency_enabled: bool = Field(default=True, description="是否启用动态并发收敛")
    crawler_resource_sample_interval_sec: float = Field(
        default=2.0, ge=0.5, le=10.0, description="资源采样间隔（秒）"
    )
    crawler_memory_pressure_warn_pct: float = Field(
        default=80.0, ge=50.0, le=99.0, description="内存压力告警阈值（%）"
    )
    crawler_memory_pressure_critical_pct: float = Field(
        default=90.0, ge=55.0, le=99.5, description="内存压力临界阈值（%）"
    )
    crawler_cpu_pressure_warn_pct: float = Field(
        default=85.0, ge=50.0, le=99.0, description="CPU 压力告警阈值（%）"
    )
    crawler_cpu_pressure_critical_pct: float = Field(
        default=95.0, ge=55.0, le=99.5, description="CPU 压力临界阈值（%）"
    )
    crawler_resource_throttle_max_factor: float = Field(
        default=3.0, ge=1.1, le=6.0, description="资源压力最大节流倍数"
    )
    # 浏览器配置
    browser_headless: Optional[bool] = Field(default=None, description="是否无头模式")
    browser_background_tabs: Optional[bool] = Field(default=None, description="是否在后台创建新标签页")
    browser_foreground_on_login: Optional[bool] = Field(default=None, description="登录失效或风控时是否自动前台唤起浏览器")
    browser_prefer_user_data_dir: Optional[bool] = Field(default=None, description="启动新浏览器时是否优先复用检测到的真实用户数据目录")
    browser_proxy: Optional[str] = Field(default=None, description="代理配置，格式：http://ip:port")
    browser_load_mode: Optional[str] = Field(default=None, description="页面加载模式：normal 或 eager")
    browser_block_images: Optional[bool] = Field(default=None, description="是否禁用图片加载")
    browser_block_videos: Optional[bool] = Field(default=None, description="是否禁用视频/流媒体加载")
    browser_stealth_enabled: Optional[bool] = Field(default=None, description="是否启用平衡档伪装脚本")
    browser_linux_hardening: Optional[bool] = Field(default=None, description="Linux 无头环境是否启用稳定性参数")
    browser_pool_auto_close_idle: Optional[bool] = Field(default=None, description="任务结束后是否自动关闭空闲浏览器实例")
    # 原始响应配置
    save_raw_responses: bool = Field(default=True, description="是否保存原始响应")
    raw_responses_max_pages: int = Field(default=0, ge=0, le=20000, description="每任务最多保存页数（0=不限制）")
    # 去重配置
    crawler_dedup_enabled: bool = Field(default=True, description="是否启用跨任务推文去重（缓存命中后跳过重复抓取）")
    weibo_auto_split_or_keywords: bool = Field(
        default=False,
        description="是否自动拆分微博简单 OR 关键词；关闭时按原样保留完整查询",
    )
    weibo_time_split_window_days: int = Field(default=7, ge=1, le=365, description="微博固定时间窗口天数")
    weibo_time_split_max_segments: int = Field(default=600, ge=1, le=2000, description="微博时间分段安全上限，超出时显式报错")
    weibo_http_418_cooldown_seconds: float = Field(
        default=600.0,
        ge=60.0,
        le=3600.0,
        description="微博命中 HTTP 418 错误页后的冷却时长（秒）",
    )
    x_auto_time_split_enabled: bool = Field(default=True, description="是否启用 X 搜索自动时间分割")
    x_time_split_trigger_days: int = Field(default=30, ge=1, le=3650, description="X 搜索时间跨度达到该值后触发时间分割")
    x_time_split_window_days: int = Field(default=7, ge=1, le=365, description="X 固定时间窗口天数")
    x_time_split_window_days_unlimited: int = Field(default=7, ge=1, le=365, description="X 无上限抓取模式下的固定时间窗口天数")
    x_time_split_max_segments: int = Field(default=600, ge=1, le=2000, description="X 时间分段安全上限，超出时显式报错")


@router.get(
    "",
    response_model=CrawlerConfig,
    summary="获取爬虫运行参数",
    description="返回当前爬虫使用的所有配置参数（已合并用户持久化设置）。",
)
async def get_crawler_config() -> CrawlerConfig:
    """获取当前爬虫配置"""
    return CrawlerConfig(
        crawler_timeout=settings.crawler_timeout,
        crawler_page_interval=settings.crawler_page_interval,
        crawler_initial_wait=settings.crawler_initial_wait,
        crawler_reply_wait=settings.crawler_reply_wait,
        crawler_preview_count=settings.crawler_preview_count,
        crawler_packet_soft_retries=settings.crawler_packet_soft_retries,
        crawler_refresh_max_retries=settings.crawler_refresh_max_retries,
        crawler_challenge_retry_times=settings.crawler_challenge_retry_times,
        crawler_challenge_cooldown=settings.crawler_challenge_cooldown,
        crawler_cloudflare_wait_seconds=settings.crawler_cloudflare_wait_seconds,
        crawler_max_concurrent_tasks=settings.crawler_max_concurrent_tasks,
        crawler_cross_platform_concurrent=settings.crawler_cross_platform_concurrent,
        scheduler_backend=settings.scheduler_backend,
        crawler_adaptive_wait_enabled=settings.crawler_adaptive_wait_enabled,
        crawler_page_interval_min=settings.crawler_page_interval_min,
        crawler_page_interval_max=settings.crawler_page_interval_max,
        crawler_interrupt_poll_ms=settings.crawler_interrupt_poll_ms,
        crawler_checkpoint_flush_interval_sec=settings.crawler_checkpoint_flush_interval_sec,
        crawler_checkpoint_reply_batch=settings.crawler_checkpoint_reply_batch,
        crawler_live_push_interval_ms=settings.crawler_live_push_interval_ms,
        crawler_active_task_watchdog_enabled=settings.crawler_active_task_watchdog_enabled,
        crawler_active_task_stale_timeout_sec=settings.crawler_active_task_stale_timeout_sec,
        crawler_active_task_watchdog_interval_sec=settings.crawler_active_task_watchdog_interval_sec,
        crawler_auto_throttle_enabled=settings.crawler_auto_throttle_enabled,
        crawler_dynamic_concurrency_enabled=settings.crawler_dynamic_concurrency_enabled,
        crawler_resource_sample_interval_sec=settings.crawler_resource_sample_interval_sec,
        crawler_memory_pressure_warn_pct=settings.crawler_memory_pressure_warn_pct,
        crawler_memory_pressure_critical_pct=settings.crawler_memory_pressure_critical_pct,
        crawler_cpu_pressure_warn_pct=settings.crawler_cpu_pressure_warn_pct,
        crawler_cpu_pressure_critical_pct=settings.crawler_cpu_pressure_critical_pct,
        crawler_resource_throttle_max_factor=settings.crawler_resource_throttle_max_factor,
        browser_headless=settings.browser_headless,
        browser_background_tabs=settings.browser_background_tabs,
        browser_foreground_on_login=settings.browser_foreground_on_login,
        browser_prefer_user_data_dir=settings.browser_prefer_user_data_dir,
        browser_proxy=settings.browser_proxy,
        browser_load_mode=settings.browser_load_mode,
        browser_block_images=settings.browser_block_images,
        browser_block_videos=settings.browser_block_videos,
        browser_stealth_enabled=settings.browser_stealth_enabled,
        browser_linux_hardening=settings.browser_linux_hardening,
        browser_pool_auto_close_idle=settings.browser_pool_auto_close_idle,
        save_raw_responses=settings.save_raw_responses,
        raw_responses_max_pages=settings.raw_responses_max_pages,
        crawler_dedup_enabled=settings.crawler_dedup_enabled,
        weibo_auto_split_or_keywords=settings.weibo_auto_split_or_keywords,
        weibo_time_split_window_days=settings.weibo_time_split_window_days,
        weibo_time_split_max_segments=settings.weibo_time_split_max_segments,
        weibo_http_418_cooldown_seconds=settings.weibo_http_418_cooldown_seconds,
        x_auto_time_split_enabled=settings.x_auto_time_split_enabled,
        x_time_split_trigger_days=settings.x_time_split_trigger_days,
        x_time_split_window_days=settings.x_time_split_window_days,
        x_time_split_window_days_unlimited=settings.x_time_split_window_days_unlimited,
        x_time_split_max_segments=settings.x_time_split_max_segments,
    )


@router.put(
    "",
    response_model=CrawlerConfig,
    summary="更新爬虫运行参数",
    description=(
        "更新爬虫配置，**立即生效并持久化到数据库**。\n\n"
        "重启服务后仍然保留用户设置（优先级高于 `.env` 默认值）。"
    ),
)
async def update_crawler_config(config: CrawlerConfig) -> CrawlerConfig:
    """更新并持久化爬虫配置"""
    # 更新内存中的 settings 单例
    settings.crawler_timeout = config.crawler_timeout
    settings.crawler_page_interval = config.crawler_page_interval
    settings.crawler_initial_wait = config.crawler_initial_wait
    settings.crawler_reply_wait = config.crawler_reply_wait
    settings.crawler_preview_count = config.crawler_preview_count
    settings.crawler_packet_soft_retries = config.crawler_packet_soft_retries
    settings.crawler_refresh_max_retries = config.crawler_refresh_max_retries
    settings.crawler_challenge_retry_times = config.crawler_challenge_retry_times
    settings.crawler_challenge_cooldown = config.crawler_challenge_cooldown
    settings.crawler_cloudflare_wait_seconds = config.crawler_cloudflare_wait_seconds
    settings.crawler_max_concurrent_tasks = config.crawler_max_concurrent_tasks
    settings.crawler_cross_platform_concurrent = config.crawler_cross_platform_concurrent
    settings.scheduler_backend = (config.scheduler_backend or "memory").strip().lower()
    if settings.scheduler_backend not in ("memory", "redis"):
        settings.scheduler_backend = "memory"
    settings.crawler_adaptive_wait_enabled = config.crawler_adaptive_wait_enabled
    settings.crawler_page_interval_min = config.crawler_page_interval_min
    settings.crawler_page_interval_max = max(config.crawler_page_interval_max, config.crawler_page_interval_min)
    settings.crawler_interrupt_poll_ms = config.crawler_interrupt_poll_ms
    settings.crawler_checkpoint_flush_interval_sec = config.crawler_checkpoint_flush_interval_sec
    settings.crawler_checkpoint_reply_batch = config.crawler_checkpoint_reply_batch
    settings.crawler_live_push_interval_ms = config.crawler_live_push_interval_ms
    settings.crawler_active_task_watchdog_enabled = config.crawler_active_task_watchdog_enabled
    settings.crawler_active_task_stale_timeout_sec = config.crawler_active_task_stale_timeout_sec
    settings.crawler_active_task_watchdog_interval_sec = config.crawler_active_task_watchdog_interval_sec
    settings.crawler_auto_throttle_enabled = config.crawler_auto_throttle_enabled
    settings.crawler_dynamic_concurrency_enabled = config.crawler_dynamic_concurrency_enabled
    settings.crawler_resource_sample_interval_sec = config.crawler_resource_sample_interval_sec
    settings.crawler_memory_pressure_warn_pct = config.crawler_memory_pressure_warn_pct
    settings.crawler_memory_pressure_critical_pct = max(
        config.crawler_memory_pressure_critical_pct,
        config.crawler_memory_pressure_warn_pct + 1.0,
    )
    settings.crawler_cpu_pressure_warn_pct = config.crawler_cpu_pressure_warn_pct
    settings.crawler_cpu_pressure_critical_pct = max(
        config.crawler_cpu_pressure_critical_pct,
        config.crawler_cpu_pressure_warn_pct + 1.0,
    )
    settings.crawler_resource_throttle_max_factor = config.crawler_resource_throttle_max_factor
    settings.save_raw_responses = config.save_raw_responses
    settings.raw_responses_max_pages = config.raw_responses_max_pages
    settings.crawler_dedup_enabled = config.crawler_dedup_enabled
    settings.weibo_auto_split_or_keywords = config.weibo_auto_split_or_keywords
    settings.weibo_time_split_window_days = config.weibo_time_split_window_days
    settings.weibo_time_split_max_segments = config.weibo_time_split_max_segments
    settings.weibo_http_418_cooldown_seconds = config.weibo_http_418_cooldown_seconds
    settings.x_auto_time_split_enabled = config.x_auto_time_split_enabled
    settings.x_time_split_trigger_days = config.x_time_split_trigger_days
    settings.x_time_split_window_days = config.x_time_split_window_days
    settings.x_time_split_window_days_unlimited = config.x_time_split_window_days_unlimited
    settings.x_time_split_max_segments = config.x_time_split_max_segments

    # 构建要持久化的设置 dict
    persist = {
        "crawler_timeout": config.crawler_timeout,
        "crawler_page_interval": config.crawler_page_interval,
        "crawler_initial_wait": config.crawler_initial_wait,
        "crawler_reply_wait": config.crawler_reply_wait,
        "crawler_preview_count": config.crawler_preview_count,
        "crawler_packet_soft_retries": config.crawler_packet_soft_retries,
        "crawler_refresh_max_retries": config.crawler_refresh_max_retries,
        "crawler_challenge_retry_times": config.crawler_challenge_retry_times,
        "crawler_challenge_cooldown": config.crawler_challenge_cooldown,
        "crawler_cloudflare_wait_seconds": config.crawler_cloudflare_wait_seconds,
        "crawler_max_concurrent_tasks": config.crawler_max_concurrent_tasks,
        "crawler_cross_platform_concurrent": settings.crawler_cross_platform_concurrent,
        "scheduler_backend": settings.scheduler_backend,
        "crawler_adaptive_wait_enabled": settings.crawler_adaptive_wait_enabled,
        "crawler_page_interval_min": settings.crawler_page_interval_min,
        "crawler_page_interval_max": settings.crawler_page_interval_max,
        "crawler_interrupt_poll_ms": settings.crawler_interrupt_poll_ms,
        "crawler_checkpoint_flush_interval_sec": settings.crawler_checkpoint_flush_interval_sec,
        "crawler_checkpoint_reply_batch": settings.crawler_checkpoint_reply_batch,
        "crawler_live_push_interval_ms": settings.crawler_live_push_interval_ms,
        "crawler_active_task_watchdog_enabled": settings.crawler_active_task_watchdog_enabled,
        "crawler_active_task_stale_timeout_sec": settings.crawler_active_task_stale_timeout_sec,
        "crawler_active_task_watchdog_interval_sec": settings.crawler_active_task_watchdog_interval_sec,
        "crawler_auto_throttle_enabled": settings.crawler_auto_throttle_enabled,
        "crawler_dynamic_concurrency_enabled": settings.crawler_dynamic_concurrency_enabled,
        "crawler_resource_sample_interval_sec": settings.crawler_resource_sample_interval_sec,
        "crawler_memory_pressure_warn_pct": settings.crawler_memory_pressure_warn_pct,
        "crawler_memory_pressure_critical_pct": settings.crawler_memory_pressure_critical_pct,
        "crawler_cpu_pressure_warn_pct": settings.crawler_cpu_pressure_warn_pct,
        "crawler_cpu_pressure_critical_pct": settings.crawler_cpu_pressure_critical_pct,
        "crawler_resource_throttle_max_factor": settings.crawler_resource_throttle_max_factor,
        "save_raw_responses": settings.save_raw_responses,
        "raw_responses_max_pages": settings.raw_responses_max_pages,
        "crawler_dedup_enabled": settings.crawler_dedup_enabled,
        "weibo_auto_split_or_keywords": settings.weibo_auto_split_or_keywords,
        "weibo_time_split_window_days": settings.weibo_time_split_window_days,
        "weibo_time_split_max_segments": settings.weibo_time_split_max_segments,
        "weibo_http_418_cooldown_seconds": settings.weibo_http_418_cooldown_seconds,
        "x_auto_time_split_enabled": settings.x_auto_time_split_enabled,
        "x_time_split_trigger_days": settings.x_time_split_trigger_days,
        "x_time_split_window_days": settings.x_time_split_window_days,
        "x_time_split_window_days_unlimited": settings.x_time_split_window_days_unlimited,
        "x_time_split_max_segments": settings.x_time_split_max_segments,
    }

    # 可选字段：只在显式传入时持久化
    if config.browser_headless is not None:
        settings.browser_headless = config.browser_headless
        persist["browser_headless"] = config.browser_headless
    if config.browser_background_tabs is not None:
        settings.browser_background_tabs = config.browser_background_tabs
        persist["browser_background_tabs"] = config.browser_background_tabs
    if config.browser_foreground_on_login is not None:
        settings.browser_foreground_on_login = config.browser_foreground_on_login
        persist["browser_foreground_on_login"] = config.browser_foreground_on_login
    if config.browser_prefer_user_data_dir is not None:
        settings.browser_prefer_user_data_dir = config.browser_prefer_user_data_dir
        persist["browser_prefer_user_data_dir"] = config.browser_prefer_user_data_dir

    if config.browser_proxy is not None:
        settings.browser_proxy = config.browser_proxy
        persist["browser_proxy"] = config.browser_proxy
    if config.browser_load_mode is not None:
        mode = config.browser_load_mode.strip().lower()
        if mode not in ("normal", "eager"):
            mode = "normal"
        settings.browser_load_mode = mode
        persist["browser_load_mode"] = mode
    if config.browser_block_images is not None:
        settings.browser_block_images = config.browser_block_images
        persist["browser_block_images"] = config.browser_block_images
    if config.browser_block_videos is not None:
        settings.browser_block_videos = config.browser_block_videos
        persist["browser_block_videos"] = config.browser_block_videos
    if config.browser_stealth_enabled is not None:
        settings.browser_stealth_enabled = config.browser_stealth_enabled
        persist["browser_stealth_enabled"] = config.browser_stealth_enabled
    if config.browser_linux_hardening is not None:
        settings.browser_linux_hardening = config.browser_linux_hardening
        persist["browser_linux_hardening"] = config.browser_linux_hardening
    if config.browser_pool_auto_close_idle is not None:
        settings.browser_pool_auto_close_idle = config.browser_pool_auto_close_idle
        persist["browser_pool_auto_close_idle"] = config.browser_pool_auto_close_idle

    # 写入数据库
    set_settings_batch(persist)
    scheduler.reconfigure_backend()

    # 同步更新浏览器池大小
    try:
        from crawler.browser_pool import compute_pool_max_size, get_browser_pool

        get_browser_pool().resize(
            compute_pool_max_size(
                settings.crawler_max_concurrent_tasks,
                cross_platform=settings.crawler_cross_platform_concurrent,
            )
        )
    except Exception:
        pass

    return CrawlerConfig(
        crawler_timeout=settings.crawler_timeout,
        crawler_page_interval=settings.crawler_page_interval,
        crawler_initial_wait=settings.crawler_initial_wait,
        crawler_reply_wait=settings.crawler_reply_wait,
        crawler_preview_count=settings.crawler_preview_count,
        crawler_packet_soft_retries=settings.crawler_packet_soft_retries,
        crawler_refresh_max_retries=settings.crawler_refresh_max_retries,
        crawler_challenge_retry_times=settings.crawler_challenge_retry_times,
        crawler_challenge_cooldown=settings.crawler_challenge_cooldown,
        crawler_cloudflare_wait_seconds=settings.crawler_cloudflare_wait_seconds,
        crawler_max_concurrent_tasks=settings.crawler_max_concurrent_tasks,
        crawler_cross_platform_concurrent=settings.crawler_cross_platform_concurrent,
        scheduler_backend=settings.scheduler_backend,
        crawler_adaptive_wait_enabled=settings.crawler_adaptive_wait_enabled,
        crawler_page_interval_min=settings.crawler_page_interval_min,
        crawler_page_interval_max=settings.crawler_page_interval_max,
        crawler_interrupt_poll_ms=settings.crawler_interrupt_poll_ms,
        crawler_checkpoint_flush_interval_sec=settings.crawler_checkpoint_flush_interval_sec,
        crawler_checkpoint_reply_batch=settings.crawler_checkpoint_reply_batch,
        crawler_live_push_interval_ms=settings.crawler_live_push_interval_ms,
        crawler_auto_throttle_enabled=settings.crawler_auto_throttle_enabled,
        crawler_dynamic_concurrency_enabled=settings.crawler_dynamic_concurrency_enabled,
        crawler_resource_sample_interval_sec=settings.crawler_resource_sample_interval_sec,
        crawler_memory_pressure_warn_pct=settings.crawler_memory_pressure_warn_pct,
        crawler_memory_pressure_critical_pct=settings.crawler_memory_pressure_critical_pct,
        crawler_cpu_pressure_warn_pct=settings.crawler_cpu_pressure_warn_pct,
        crawler_cpu_pressure_critical_pct=settings.crawler_cpu_pressure_critical_pct,
        crawler_resource_throttle_max_factor=settings.crawler_resource_throttle_max_factor,
        browser_headless=settings.browser_headless,
        browser_background_tabs=settings.browser_background_tabs,
        browser_foreground_on_login=settings.browser_foreground_on_login,
        browser_prefer_user_data_dir=settings.browser_prefer_user_data_dir,
        browser_proxy=settings.browser_proxy,
        browser_load_mode=settings.browser_load_mode,
        browser_block_images=settings.browser_block_images,
        browser_block_videos=settings.browser_block_videos,
        browser_stealth_enabled=settings.browser_stealth_enabled,
        browser_linux_hardening=settings.browser_linux_hardening,
        browser_pool_auto_close_idle=settings.browser_pool_auto_close_idle,
        save_raw_responses=settings.save_raw_responses,
        raw_responses_max_pages=settings.raw_responses_max_pages,
        crawler_dedup_enabled=settings.crawler_dedup_enabled,
        weibo_auto_split_or_keywords=settings.weibo_auto_split_or_keywords,
        weibo_time_split_window_days=settings.weibo_time_split_window_days,
        weibo_time_split_max_segments=settings.weibo_time_split_max_segments,
        weibo_http_418_cooldown_seconds=settings.weibo_http_418_cooldown_seconds,
        x_auto_time_split_enabled=settings.x_auto_time_split_enabled,
        x_time_split_trigger_days=settings.x_time_split_trigger_days,
        x_time_split_window_days=settings.x_time_split_window_days,
        x_time_split_window_days_unlimited=settings.x_time_split_window_days_unlimited,
        x_time_split_max_segments=settings.x_time_split_max_segments,
    )
