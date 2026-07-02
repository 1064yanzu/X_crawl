"""
FastAPI 应用入口（升级版）
新增：断点续爬检查点路由
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from api.routers import search, tasks, checkpoints
from api.routers import raw_responses as raw_responses_router
from api.routers import cookies as cookies_router
from api.routers import export as export_router
from api.routers import batch_export as batch_export_router
from api.routers import crawler_config as crawler_config_router
from api.routers import failed_replies as failed_replies_router
from api.routers import browser_selector as browser_selector_router
from api.routers import accounts as accounts_router
from api.routers import weibo_cookies as weibo_cookies_router
from api.routers import weibo_accounts as weibo_accounts_router
from api.routers import comment_backfill as comment_backfill_router
from api.routers import comment_backfill_group as comment_backfill_group_router
from api.routers import task_queues as task_queues_router
from api.routers import batch_import as batch_import_router
from api.routers import concurrent_search as concurrent_search_router
from api.routers import browser_pool as browser_pool_router
from api.routers import analytics as analytics_router
from api.routers import youtube_api_keys as youtube_api_keys_router
from api.routers import system as system_router
from crawler.browser import close_browser, maybe_cleanup_stale_linux_browsers
from crawler.browser_detector import detect_all
from crawler.log_config import setup_logging
from config import settings, ensure_data_dirs

# 启动前确保数据目录就绪（桌面端模式下 data_dir 来自 XCRAWL_DATA_DIR 环境变量）
ensure_data_dirs()

# 初始化结构化日志（控制台 + 文件轮转）
setup_logging()
logger = logging.getLogger(__name__)

# 开发模式探测：仅 XCRAWL_DEV_MODE=1 时才开启 /docs 与宽松 CORS、保留异常 stack
_DEV_MODE = os.environ.get("XCRAWL_DEV_MODE", "").strip() == "1"


def _resolve_cors_origins() -> list[str]:
    raw = os.environ.get("XCRAWL_CORS_ORIGINS", "").strip()
    if _DEV_MODE and not raw:
        return ["*"]
    if not raw:
        # 默认仅本地环回（桌面端通过 127.0.0.1 走环回，前端打包后的 /xapi 走同源）
        return [
            "http://127.0.0.1",
            "http://localhost",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:3721",
            "http://localhost:3721",
        ]
    return [item.strip() for item in raw.split(",") if item.strip()]


_CORS_ORIGINS = _resolve_cors_origins()
_CORS_ALLOW_ALL = "*" in _CORS_ORIGINS
# 桌面端会被动态分配前端端口，因此用 regex 放行所有本地端口
_CORS_REGEX = None if _CORS_ALLOW_ALL else r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("X_crawl API 服务启动...")
    cleanup = maybe_cleanup_stale_linux_browsers(reason="api_startup")
    if int(cleanup.get("killed_roots") or 0) > 0:
        logger.warning(
            "启动前已清理残留浏览器实例: roots=%s, processes=%s, mem_avail=%sMB",
            cleanup.get("killed_roots"),
            cleanup.get("killed_processes"),
            cleanup.get("host_mem_available_mb"),
        )
    # 启动时检测浏览器环境（仅日志，不初始化实例）
    detected = detect_all()
    logger.info(
        f"浏览器检测: path={'✅' if detected['browser_path'] else '❌'} "
        f"| user_data={'✅' if detected['user_data_path'] else '⚠️'} "
        f"| platform={detected['platform']}"
    )

    # 启动时执行一次 raw_responses 滚动清理，并拉起后台周期清理守护
    try:
        from crawler.response_saver import cleanup_old_responses, start_cleanup_daemon
        cleanup_old_responses()
        if settings.raw_responses_cleanup_enabled:
            start_cleanup_daemon()
    except Exception as cleanup_err:
        logger.warning(f"启动 raw_responses 清理失败（非致命）: {cleanup_err}")

    # 启动任务数据库 WAL 周期维护（checkpoint TRUNCATE）
    try:
        from api.services.task_db import start_db_maintenance
        start_db_maintenance()
    except Exception as db_err:
        logger.warning(f"启动数据库 WAL 维护失败（非致命）: {db_err}")

    # 启动浏览器生命周期守护线程（健康心跳 + debug 清理）
    try:
        from crawler.browser_lifecycle import start_all as start_lifecycle
        start_lifecycle()
    except Exception as e:
        logger.warning("启动浏览器生命周期守护失败（非致命）: %s", e)
    yield
    logger.info("正在关闭浏览器并释放资源...")
    try:
        from crawler.response_saver import stop_cleanup_daemon
        stop_cleanup_daemon()
    except Exception:
        pass
    try:
        from api.services.task_db import stop_db_maintenance
        stop_db_maintenance()
    except Exception:
        pass
    try:
        from crawler.browser_lifecycle import stop_all as stop_lifecycle
        stop_lifecycle()
    except Exception:
        pass
    try:
        from crawler.browser_pool import set_shutting_down
        set_shutting_down()
    except Exception:
        pass
    close_browser()
    try:
        from crawler.browser_pool import get_browser_pool, is_pool_mode_enabled
        if is_pool_mode_enabled():
            get_browser_pool().close_all()
    except Exception:
        pass
    logger.info("X_crawl API 服务已关闭")


app = FastAPI(
    title="X_crawl API",
    description=(
        "基于 DrissionPage 网络监听的 X/Twitter 爬虫 API。\n\n"
        "**亮点功能**：\n"
        "- 🌐 跨平台（macOS / Windows / Linux），自动检测已安装浏览器\n"
        "- ♻️ 断点续爬：任务中断后携带 `task_id` 恢复，已爬数据不丢失\n"
        "- 📊 完整字段：推文/用户/媒体全字段解析，含视频全清晰度变体\n"
        "- ⚡ 异步任务：后台爬取，HTTP 接口立即响应\n\n"
        "**快速上手**：\n"
        "1. `POST /api/v1/search` → 获取 `task_id`\n"
        "2. `GET /api/v1/search/{task_id}` → 轮询，`status=done` 时获取推文\n"
        "3. 若中断可 `GET /api/v1/checkpoints` 查看断点，再次 POST 带上 `task_id` 恢复\n\n"
        "💾 原始响应归档：`GET /api/v1/raw-responses` 查看已保存的原始 JSON 文件"
    ),
    version="1.1.1",
    lifespan=lifespan,
    docs_url="/docs" if _DEV_MODE else None,
    redoc_url="/redoc" if _DEV_MODE else None,
    openapi_url="/openapi.json" if _DEV_MODE else None,
)

if _CORS_ALLOW_ALL:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_origin_regex=_CORS_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

# 挂载调试截图静态目录
debug_dir = Path(__file__).parent.parent / "logs" / "debug"
debug_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/v1/debug", StaticFiles(directory=str(debug_dir)), name="debug")

app.include_router(search.router)
app.include_router(tasks.router)
app.include_router(checkpoints.router)
app.include_router(raw_responses_router.router)
app.include_router(cookies_router.router)
app.include_router(export_router.router)
app.include_router(batch_export_router.router)
app.include_router(crawler_config_router.router)
app.include_router(failed_replies_router.router)
app.include_router(browser_selector_router.router)
app.include_router(accounts_router.router)
app.include_router(weibo_cookies_router.router)
app.include_router(weibo_accounts_router.router)
app.include_router(comment_backfill_router.router)
app.include_router(comment_backfill_group_router.router)
app.include_router(task_queues_router.router)
app.include_router(batch_import_router.router)
app.include_router(concurrent_search_router.router)
app.include_router(browser_pool_router.router)
app.include_router(analytics_router.router)
app.include_router(youtube_api_keys_router.router)
app.include_router(system_router.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    trace_id = uuid.uuid4().hex[:12]
    logger.error(
        f"未处理的异常 trace_id={trace_id} path={request.url.path}: {exc}",
        exc_info=True,
    )
    if _DEV_MODE:
        # 开发模式仍把异常信息直接返回，方便调试
        return JSONResponse(
            status_code=500,
            content={"detail": f"服务内部错误: {exc}", "trace_id": trace_id},
        )
    # 生产模式只返回脱敏后的结构，完整 stack 写日志
    return JSONResponse(
        status_code=500,
        content={"detail": "服务内部错误，请稍后重试", "trace_id": trace_id},
    )


@app.get("/", tags=["健康检查"])
async def root():
    return {
        "status": "ok",
        "service": "X_crawl API",
        "version": "1.1.1",
        "features": ["cross-platform", "checkpoint-resume", "full-fields", "async-tasks"],
        "docs": "/docs",
    }


@app.get("/health", tags=["健康检查"])
async def health():
    """返回服务健康状态及浏览器检测信息"""
    detected = detect_all()
    return {
        "status": "healthy",
        "browser_detected": detected["browser_path"] is not None,
        "browser_path": detected["browser_path"],
        "user_data_detected": detected["user_data_path"] is not None,
        "platform": detected["platform"],
        "save_raw_responses": settings.save_raw_responses,
        "raw_responses_dir": settings.raw_responses_dir,
    }
