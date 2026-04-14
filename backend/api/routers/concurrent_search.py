"""
并发搜索路由 - 多账号并发爬取

API 端点：
- POST /api/v1/concurrent/search - 创建并发搜索任务
- GET /api/v1/concurrent/status - 查询并发爬取状态
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.services import task_manager
from api.services.crawl_service import start_crawler_thread
from crawler.account_dispatcher import get_dispatcher
from crawler.account_pool import get_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/concurrent", tags=["并发爬取"])


class ConcurrentSearchRequest(BaseModel):
    """并发搜索请求"""
    keywords: List[str] = Field(..., description="搜索关键词列表")
    product: str = Field(default="Top", description="搜索类型")
    fetch_replies: bool = Field(default=False, description="是否爬取回复")
    max_replies_per_tweet: int = Field(default=20, description="每条推文的最大回复数")
    reply_depth: int = Field(default=2, description="回复深度")
    crawl_strategy: str = Field(default="dfs", description="爬取策略")
    platform: str = Field(default="x", description="平台")
    time_split_mode: str = Field(default="inherit", description="时间拆分策略")
    time_split_window_days: Optional[int] = Field(default=None, description="任务级时间拆分窗口天数")
    time_split_max_segments: Optional[int] = Field(default=None, description="任务级时间拆分最大分段数")


class ConcurrentSearchResponse(BaseModel):
    """并发搜索响应"""
    task_ids: List[str]
    total_tasks: int
    assigned_accounts: int


@router.post("/search", response_model=ConcurrentSearchResponse)
async def create_concurrent_search(req: ConcurrentSearchRequest):
    """创建并发搜索任务，自动分配账号"""
    if not req.keywords:
        raise HTTPException(status_code=400, detail="关键词列表不能为空")

    if len(req.keywords) > 50:
        raise HTTPException(status_code=400, detail="最多支持 50 个关键词")

    pool = get_pool()
    if pool.total_count() == 0:
        raise HTTPException(status_code=400, detail="没有可用账号")

    task_ids = []
    dispatcher = get_dispatcher()

    for keyword in req.keywords:
        task_id = task_manager.create_task(
            keyword=keyword,
            product=req.product,
            fetch_replies=req.fetch_replies,
            max_replies_per_tweet=req.max_replies_per_tweet,
            reply_depth=req.reply_depth,
            crawl_strategy=req.crawl_strategy,
            platform=req.platform,
            time_split_mode=req.time_split_mode,
            time_split_window_days=req.time_split_window_days,
            time_split_max_segments=req.time_split_max_segments,
        )

        account = dispatcher.assign_account(task_id)
        if account:
            task_manager.bind_account(task_id, account.account_id, account.alias)

        task = task_manager.get_task(task_id)
        start_crawler_thread(task_id, task)
        task_ids.append(task_id)

    assignments = dispatcher.get_active_assignments()
    assigned_accounts = len(set(a.account_id for a in assignments))

    return ConcurrentSearchResponse(
        task_ids=task_ids,
        total_tasks=len(task_ids),
        assigned_accounts=assigned_accounts,
    )


@router.get("/status")
async def get_concurrent_status():
    """查询并发爬取状态"""
    dispatcher = get_dispatcher()
    return dispatcher.get_account_status()
