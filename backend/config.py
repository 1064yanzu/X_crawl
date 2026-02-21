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
    browser_headless: bool = Field(
        default=False, description="是否无头模式"
    )

    # API 配置
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_debug: bool = Field(default=True)

    # 爬虫配置
    crawler_timeout: float = Field(
        default=30.0, description="等待数据包超时时间（秒）"
    )
    crawler_page_interval: float = Field(
        default=2.0, description="翻页操作间隔（秒）"
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


settings = Settings()
