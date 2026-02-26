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
    crawler_max_concurrent_tasks: int = Field(description="并发运行任务上限", ge=1, le=5)
    scheduler_backend: str = Field(default="memory", description="调度后端：memory/redis")
    crawler_adaptive_wait_enabled: bool = Field(default=True, description="是否启用自适应等待")
    crawler_page_interval_min: float = Field(default=2.5, ge=0.5, le=120.0, description="翻页间隔下限（秒）")
    crawler_page_interval_max: float = Field(default=8.0, ge=0.5, le=180.0, description="翻页间隔上限（秒）")
    crawler_interrupt_poll_ms: int = Field(default=300, ge=50, le=3000, description="中断轮询粒度（毫秒）")
    # 浏览器配置
    browser_headless: Optional[bool] = Field(default=None, description="是否无头模式")
    browser_proxy: Optional[str] = Field(default=None, description="代理配置，格式：http://ip:port")
    browser_load_mode: Optional[str] = Field(default=None, description="页面加载模式：normal 或 eager")
    browser_block_images: Optional[bool] = Field(default=None, description="是否禁用图片加载")


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
        crawler_max_concurrent_tasks=settings.crawler_max_concurrent_tasks,
        scheduler_backend=settings.scheduler_backend,
        crawler_adaptive_wait_enabled=settings.crawler_adaptive_wait_enabled,
        crawler_page_interval_min=settings.crawler_page_interval_min,
        crawler_page_interval_max=settings.crawler_page_interval_max,
        crawler_interrupt_poll_ms=settings.crawler_interrupt_poll_ms,
        browser_headless=settings.browser_headless,
        browser_proxy=settings.browser_proxy,
        browser_load_mode=settings.browser_load_mode,
        browser_block_images=settings.browser_block_images,
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
    settings.crawler_max_concurrent_tasks = config.crawler_max_concurrent_tasks
    settings.scheduler_backend = (config.scheduler_backend or "memory").strip().lower()
    if settings.scheduler_backend not in ("memory", "redis"):
        settings.scheduler_backend = "memory"
    settings.crawler_adaptive_wait_enabled = config.crawler_adaptive_wait_enabled
    settings.crawler_page_interval_min = config.crawler_page_interval_min
    settings.crawler_page_interval_max = max(config.crawler_page_interval_max, config.crawler_page_interval_min)
    settings.crawler_interrupt_poll_ms = config.crawler_interrupt_poll_ms

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
        "crawler_max_concurrent_tasks": config.crawler_max_concurrent_tasks,
        "scheduler_backend": settings.scheduler_backend,
        "crawler_adaptive_wait_enabled": settings.crawler_adaptive_wait_enabled,
        "crawler_page_interval_min": settings.crawler_page_interval_min,
        "crawler_page_interval_max": settings.crawler_page_interval_max,
        "crawler_interrupt_poll_ms": settings.crawler_interrupt_poll_ms,
    }

    # 可选字段：只在显式传入时持久化
    if config.browser_headless is not None:
        settings.browser_headless = config.browser_headless
        persist["browser_headless"] = config.browser_headless

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

    # 写入数据库
    set_settings_batch(persist)
    scheduler.reconfigure_backend()

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
        crawler_max_concurrent_tasks=settings.crawler_max_concurrent_tasks,
        scheduler_backend=settings.scheduler_backend,
        crawler_adaptive_wait_enabled=settings.crawler_adaptive_wait_enabled,
        crawler_page_interval_min=settings.crawler_page_interval_min,
        crawler_page_interval_max=settings.crawler_page_interval_max,
        crawler_interrupt_poll_ms=settings.crawler_interrupt_poll_ms,
        browser_headless=settings.browser_headless,
        browser_proxy=settings.browser_proxy,
        browser_load_mode=settings.browser_load_mode,
        browser_block_images=settings.browser_block_images,
    )
