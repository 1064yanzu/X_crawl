"""
全局配置模块
支持从 .env 文件读取配置
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 浏览器配置
    browser_debug_port: int = Field(
        default=9222, description="Chrome 远程调试端口（接管模式用），对应 --remote-debugging-port"
    )
    browser_user_data_path: str = Field(
        default="", description="浏览器用户数据目录，留空时优先尝试接管调试端口，其次使用爬虫专用隔离目录"
    )
    browser_exec_path: str = Field(
        default="", description="浏览器可执行文件路径，留空自动检测"
    )
    browser_proxy: str = Field(
        default="", description="代理配置，格式：http://ip:port"
    )
    browser_selected_id: str = Field(
        default="", description="用户选择的浏览器 ID（如 chrome、edge），留空则自动检测"
    )
    browser_headless: bool = Field(
        default=False, description="是否无头模式"
    )

    # API 配置
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_debug: bool = Field(default=True)

    # 爬虫配置
    crawler_timeout: float = Field(
        default=45.0, description="等待数据包超时时间（秒），适当加大以减少误判"
    )
    crawler_page_interval: float = Field(
        default=5.0, description="翻页操作间隔（秒），适当放慢避免触发反爬"
    )
    crawler_initial_wait: float = Field(
        default=3.0, description="页面首次访问后额外等待时间（秒），确保初始内容完全加载"
    )
    crawler_reply_wait: float = Field(
        default=4.0, description="评论区每次翻页后额外等待时间（秒），确保评论内容完全加载"
    )
    crawler_preview_count: int = Field(
        default=10, description="实时数据预览展示的最大条数，避免前端性能问题"
    )

    # 原始响应持久化配置
    save_raw_responses: bool = Field(
        default=True, description="是否将原始 API 响应 JSON 保存到磁盘"
    )
    raw_responses_dir: str = Field(
        default="raw_responses", description="原始响应存储根目录（相对于 backend/ 或绝对路径）"
    )
    raw_responses_max_pages: int = Field(
        default=0, description="每任务最多保存页数，0 = 不限制"
    )

    # 任务历史数据库
    tasks_db_path: str = Field(
        default="tasks.db", description="任务历史 SQLite 数据库路径（相对于 backend/ 或绝对路径）"
    )


settings = Settings()


def apply_user_settings() -> None:
    """
    从数据库加载用户设置，覆盖 .env 默认值。
    用户在设置界面配置的值优先级最高。
    应在数据库初始化之后调用。
    """
    try:
        from api.services.settings_db import get_all_settings
        user_settings = get_all_settings()
        if not user_settings:
            return

        applied = []
        for key, value in user_settings.items():
            if hasattr(settings, key):
                try:
                    setattr(settings, key, value)
                    applied.append(key)
                except Exception:
                    pass  # 类型不匹配等异常忽略

        if applied:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"已加载用户持久化设置（覆盖 .env）: {', '.join(applied)}")
    except Exception:
        pass  # 数据库未初始化时静默跳过
