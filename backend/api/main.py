"""
FastAPI 应用入口（升级版）
新增：断点续爬检查点路由
"""
import logging
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
from crawler.browser import close_browser, maybe_cleanup_stale_linux_browsers
from crawler.browser_detector import detect_all
from crawler.log_config import setup_logging
from config import settings

# 初始化结构化日志（控制台 + 文件轮转）
setup_logging()
logger = logging.getLogger(__name__)


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
    # 启动浏览器生命周期守护线程（健康心跳 + debug 清理）
    try:
        from crawler.browser_lifecycle import start_all as start_lifecycle
        start_lifecycle()
    except Exception as e:
        logger.warning("启动浏览器生命周期守护失败（非致命）: %s", e)
    yield
    logger.info("正在关闭浏览器并释放资源...")
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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务内部错误: {str(exc)}"},
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
