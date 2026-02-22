"""
爬虫参数配置路由

GET  /api/v1/crawler-config        获取当前爬虫配置
PUT  /api/v1/crawler-config        更新爬虫配置（运行时热更新，本次服务生命周期内有效）
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from config import settings

router = APIRouter(prefix="/api/v1/crawler-config", tags=["爬虫配置"])


class CrawlerConfig(BaseModel):
    """爬虫运行参数"""
    crawler_timeout: float = Field(description="等待数据包超时时间（秒）", ge=5.0, le=120.0)
    crawler_page_interval: float = Field(description="翻页操作间隔（秒）", ge=1.0, le=60.0)
    crawler_initial_wait: float = Field(description="页面首次加载后额外等待（秒）", ge=0.0, le=30.0)
    crawler_reply_wait: float = Field(description="评论区每次翻页后额外等待（秒）", ge=0.0, le=30.0)
    crawler_preview_count: int = Field(description="实时预览最大展示条数", ge=1, le=50)


@router.get(
    "",
    response_model=CrawlerConfig,
    summary="获取爬虫运行参数",
    description="返回当前爬虫使用的所有时间间隔及预览相关配置。",
)
async def get_crawler_config() -> CrawlerConfig:
    """获取当前爬虫配置"""
    return CrawlerConfig(
        crawler_timeout=settings.crawler_timeout,
        crawler_page_interval=settings.crawler_page_interval,
        crawler_initial_wait=settings.crawler_initial_wait,
        crawler_reply_wait=settings.crawler_reply_wait,
        crawler_preview_count=settings.crawler_preview_count,
    )


@router.put(
    "",
    response_model=CrawlerConfig,
    summary="更新爬虫运行参数",
    description=(
        "热更新爬虫参数，立即对之后启动的新任务生效（无需重启服务）。\n\n"
        "注意：更新仅在服务运行期间有效，服务重启后将恢复 `.env` 中的配置。\n\n"
        "如需永久保存，请同步修改后端 `.env` 文件。"
    ),
)
async def update_crawler_config(config: CrawlerConfig) -> CrawlerConfig:
    """热更新爬虫配置"""
    settings.crawler_timeout = config.crawler_timeout
    settings.crawler_page_interval = config.crawler_page_interval
    settings.crawler_initial_wait = config.crawler_initial_wait
    settings.crawler_reply_wait = config.crawler_reply_wait
    settings.crawler_preview_count = config.crawler_preview_count
    return config
