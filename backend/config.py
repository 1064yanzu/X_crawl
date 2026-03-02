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
    browser_load_mode: str = Field(
        default="normal", description="页面加载模式：normal/eager"
    )
    browser_block_images: bool = Field(
        default=False, description="是否禁用图片加载（稳健模式建议关闭）"
    )
    browser_stealth_enabled: bool = Field(
        default=False, description="是否启用轻量伪装注入（默认关闭，按需开启）"
    )
    browser_linux_hardening: bool = Field(
        default=True, description="Linux 无头模式下是否启用稳定性启动参数"
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
    crawler_packet_soft_retries: int = Field(
        default=2, description="监听数据包超时后的软重试次数"
    )
    crawler_refresh_max_retries: int = Field(
        default=3, description="软重试失败后的硬刷新重试次数"
    )
    crawler_challenge_retry_times: int = Field(
        default=2, description="检测到风控挑战页时自动重试次数"
    )
    crawler_challenge_cooldown: float = Field(
        default=8.0, description="挑战页重试前冷却时间（秒）"
    )
    crawler_max_concurrent_tasks: int = Field(
        default=1, description="允许并发运行的任务数上限（1 表示串行）"
    )
    scheduler_backend: str = Field(
        default="memory", description="任务调度后端：memory/redis（当前 redis 为预留）"
    )
    crawler_adaptive_wait_enabled: bool = Field(
        default=True, description="是否启用自适应等待区间（对翻页间隔做上下限约束）"
    )
    crawler_page_interval_min: float = Field(
        default=2.5, description="翻页间隔下限（秒），自适应等待启用时生效"
    )
    crawler_page_interval_max: float = Field(
        default=8.0, description="翻页间隔上限（秒），自适应等待启用时生效"
    )
    crawler_interrupt_poll_ms: int = Field(
        default=300, description="中断可响应睡眠的轮询粒度（毫秒）"
    )
    crawler_checkpoint_flush_interval_sec: float = Field(
        default=4.0, description="DFS 回复阶段检查点最久刷新间隔（秒）"
    )
    crawler_checkpoint_reply_batch: int = Field(
        default=3, description="DFS 回复阶段每累计多少条回复结果触发一次检查点刷新"
    )
    crawler_dedup_enabled: bool = Field(
        default=True, description="是否启用跨任务推文去重（评论缓存命中后跳过重复抓取）"
    )
    crawler_live_push_interval_ms: int = Field(
        default=800, description="SSE 实时推送间隔（毫秒）"
    )
    crawler_auto_throttle_enabled: bool = Field(
        default=True, description="是否根据系统资源压力自动放慢抓取节奏"
    )
    crawler_dynamic_concurrency_enabled: bool = Field(
        default=True, description="是否根据资源压力动态收敛并发任务上限"
    )
    crawler_resource_sample_interval_sec: float = Field(
        default=2.0, description="系统资源采样间隔（秒）"
    )
    crawler_memory_pressure_warn_pct: float = Field(
        default=80.0, description="内存压力告警阈值（%）"
    )
    crawler_memory_pressure_critical_pct: float = Field(
        default=90.0, description="内存压力临界阈值（%）"
    )
    crawler_cpu_pressure_warn_pct: float = Field(
        default=85.0, description="CPU 压力告警阈值（%）"
    )
    crawler_cpu_pressure_critical_pct: float = Field(
        default=95.0, description="CPU 压力临界阈值（%）"
    )
    crawler_resource_throttle_max_factor: float = Field(
        default=3.0, description="资源压力下最大节流倍数"
    )

    # 日志配置
    log_dir: str = Field(
        default="", description="日志文件目录（留空使用 backend/logs/）"
    )
    log_level: str = Field(
        default="INFO", description="文件日志级别: DEBUG/INFO/WARNING/ERROR"
    )
    log_max_bytes: int = Field(
        default=10485760, description="单个日志文件最大字节数，默认 10MB"
    )
    log_backup_count: int = Field(
        default=5, description="日志文件保留份数"
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

    # 浏览器健康与长时间运行配置
    browser_restart_every_n_pages: int = Field(
        default=500,
        description="每完成 N 次页面导航后触发浏览器重启（防内存泄漏，0=禁用）"
    )

    # 休息节律配置（百万级数据爬取专项）
    crawler_enable_break_rhythm: bool = Field(
        default=True, description="是否启用休息节律（防长时间爬取被识别）"
    )
    crawler_micro_break_chance: float = Field(
        default=0.15, description="微休息触发概率（每批新推文后）"
    )
    crawler_short_break_every_n: int = Field(
        default=250, description="小憩触发阈值（累计推文数）"
    )
    crawler_long_rest_interval_hours: float = Field(
        default=2.0, description="长休息间隔（小时），运行满此时间后强制休息 15-25 分钟"
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
