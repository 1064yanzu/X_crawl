"""
结构化日志配置模块
- 控制台: INFO 级别, 彩色简洁格式
- 文件:   DEBUG 级别, RotatingFileHandler (10MB × 5)
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import settings


# ---- 默认值（可通过 config.py / .env 覆盖）----
_DEFAULT_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
)
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_BACKUP_COUNT = 5
_DEFAULT_LOG_LEVEL = "DEBUG"

# ---- 格式 ----
_CONSOLE_FMT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
_FILE_FMT = (
    "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"
)
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def setup_logging() -> None:
    """
    初始化全局日志系统。只执行一次。
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    log_dir = getattr(settings, "log_dir", "") or _DEFAULT_LOG_DIR
    log_level_str = getattr(settings, "log_level", "") or _DEFAULT_LOG_LEVEL
    max_bytes = getattr(settings, "log_max_bytes", 0) or _DEFAULT_MAX_BYTES
    backup_count = getattr(settings, "log_backup_count", 0) or _DEFAULT_BACKUP_COUNT

    log_level = getattr(logging, log_level_str.upper(), logging.DEBUG)

    # 确保日志目录存在
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = os.path.join(log_dir, "xcrawl.log")

    # ---- root logger ----
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # root 设最低, 让 handler 决定过滤

    # 移除已有的 handler（避免重复）
    root.handlers.clear()

    # ---- 控制台 handler ----
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FMT, _DATE_FMT))
    root.addHandler(console_handler)

    # ---- 文件 handler ----
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(_FILE_FMT, _DATE_FMT))
    root.addHandler(file_handler)

    # 降低第三方库日志级别
    for noisy in ("urllib3", "httpcore", "httpx", "websockets", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        f"日志系统已初始化 | 文件: {log_file} | 级别: {log_level_str.upper()}"
    )
