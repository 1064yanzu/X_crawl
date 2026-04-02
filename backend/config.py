"""
全局配置模块
支持从 .env 文件读取配置
"""
import sys

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
    browser_background_tabs: bool = Field(
        default=(sys.platform == "darwin"),
        description="新标签页是否以后台方式创建（macOS 默认开启，减少浏览器抢前台焦点）"
    )
    browser_foreground_on_login: bool = Field(
        default=True,
        description="检测到登录失效或风控需人工处理时，是否自动将浏览器切到前台"
    )
    browser_prefer_user_data_dir: bool = Field(
        default=True,
        description="启动新浏览器时，是否优先复用检测到的真实用户数据目录；被占用时自动回退到爬虫专用 Profile"
    )
    browser_load_mode: str = Field(
        default="normal", description="页面加载模式：normal/eager"
    )
    browser_block_images: bool = Field(
        default=False, description="是否禁用图片加载（稳健模式建议关闭）"
    )
    browser_block_videos: bool = Field(
        default=False, description="是否禁用视频/流媒体加载（用于节省流量）"
    )
    browser_stealth_enabled: bool = Field(
        default=False, description="是否启用轻量伪装注入（默认关闭，按需开启）"
    )
    browser_linux_hardening: bool = Field(
        default=True, description="Linux 无头模式下是否启用稳定性启动参数"
    )
    browser_pool_auto_close_idle: bool = Field(
        default=True, description="浏览器池中的空闲实例是否在任务结束后自动关闭"
    )
    browser_linux_stale_cleanup_enabled: bool = Field(
        default=True, description="Linux 内存紧张时是否自动清理爬虫残留浏览器实例"
    )
    browser_linux_stale_cleanup_available_mb: float = Field(
        default=1536.0, description="Linux 残留浏览器清理触发可用内存阈值（MB）"
    )
    browser_linux_stale_cleanup_drop_mb: float = Field(
        default=512.0, description="Linux 可用内存短时骤降多少 MB 时触发残留浏览器清理"
    )
    browser_linux_stale_cleanup_max_age_sec: float = Field(
        default=900.0, description="Linux 残留浏览器实例判定最小存活时长（秒）"
    )
    browser_linux_stale_cleanup_cooldown_sec: float = Field(
        default=45.0, description="Linux 残留浏览器清理最小冷却时间（秒）"
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
        default=5, description="检测到风控挑战页时自动重试次数（含 Cloudflare 验证等待）"
    )
    crawler_challenge_cooldown: float = Field(
        default=8.0, description="挑战页重试前冷却时间（秒）"
    )
    crawler_cloudflare_wait_seconds: float = Field(
        default=60.0, description="检测到 Cloudflare 验证时每次等待时长（秒），给用户充足时间完成验证"
    )
    crawler_error_freeze_threshold: int = Field(
        default=15, description="连续错误页累计次数达到此阈值后触发长时间冻结"
    )
    crawler_error_freeze_seconds: float = Field(
        default=600.0, description="连续错误触发冻结后的休眠时长（秒），默认 10 分钟"
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
        default=0.05, description="微休息触发概率（每批新推文后）"
    )
    crawler_short_break_every_n: int = Field(
        default=500, description="小憩触发阈值（累计推文数）"
    )
    crawler_long_rest_interval_hours: float = Field(
        default=2.0, description="长休息间隔（小时），运行满此时间后强制休息 15-25 分钟"
    )

    # 任务历史数据库
    tasks_db_path: str = Field(
        default="tasks.db", description="任务历史 SQLite 数据库路径（相对于 backend/ 或绝对路径）"
    )

    # 多账号池配置
    account_pool_enabled: bool = Field(
        default=True, description="多账号池总开关（False 时退化为单账号 ensure_login 模式）"
    )
    account_rotation_every_n_pages: int = Field(
        default=0, description="搜索时每隔 N 页主动切换账号（0 = 禁用，搜索默认单账号贯穿，仅限速时才切换）"
    )
    account_rotation_multiplier_threshold: float = Field(
        default=2.0, description="搜索速率倍数超过此值时紧急切换账号"
    )
    account_rate_limit_wait_threshold_sec: float = Field(
        default=300.0,
        description=(
            "账号限速等待阈值（秒）：等待时间 ≤ 此值则等待账号恢复后继续；"
            "> 此值则冻结账号并将剩余推文转给其他账号"
        )
    )

    # 微博爬虫配置
    weibo_search_page_interval: float = Field(
        default=6.0, description="微博搜索翻页间隔（秒）"
    )
    weibo_comment_page_interval: float = Field(
        default=4.0, description="微博评论翻页间隔（秒）"
    )
    weibo_max_pages: int = Field(
        default=50, description="微博搜索最大页数（每次搜索最多 50 页）"
    )
    weibo_fetch_sub_comments: bool = Field(
        default=True, description="微博是否抓取评论（默认开启）"
    )
    weibo_max_comments_per_post: int = Field(
        default=500, description="微博每条帖子最多抓取评论数（0=不限制）"
    )
    weibo_sub_comment_max_pages: int = Field(
        default=200, description="微博单条顶层评论子评论最大翻页数（安全上限）"
    )
    weibo_auto_split_or_keywords: bool = Field(
        default=True,
        description="微博是否自动拆分简单 OR 关键词（默认开启，避免 OR 直传导致搜索不稳定）",
    )
    weibo_time_split_window_days: int = Field(
        default=7, description="微博时间分段固定窗口天数"
    )
    weibo_time_split_max_segments: int = Field(
        default=600, description="微博时间分段安全上限（超出时显式报错）"
    )
    weibo_http_418_cooldown_seconds: float = Field(
        default=600.0, description="微博命中浏览器 HTTP 418 错误页后的冷却时长（秒）"
    )
    x_auto_time_split_enabled: bool = Field(
        default=True, description="X 搜索是否自动启用时间分割"
    )
    x_time_split_trigger_days: int = Field(
        default=30, description="X 搜索时间跨度达到多少天后触发自动时间分割"
    )
    x_time_split_window_days: int = Field(
        default=7, description="X 固定时间窗口覆盖天数"
    )
    x_time_split_window_days_unlimited: int = Field(
        default=7, description="X 无上限抓取模式下每个时间窗覆盖天数"
    )
    x_time_split_max_segments: int = Field(
        default=600, description="X 时间分段安全上限（超出时显式报错）"
    )



    # ─── 并发爬取配置 ──────────────────────────────────────────────────────────
    concurrent_crawl_enabled: bool = Field(
        default=True, description="是否启用并发爬取功能"
    )
    account_assignment_strategy: str = Field(
        default="round_robin", description="账号分配策略: round_robin 或 least_used"
    )
    account_reuse_delay_sec: float = Field(
        default=0.0, description="账号释放后的重用延迟（秒）"
    )
    account_max_concurrent_tasks: int = Field(
        default=1, description="每个账号最多同时执行的任务数"
    )
    crawler_cross_platform_concurrent: bool = Field(
        default=True, description="是否允许 X 和微博任务跨平台并发执行"
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
