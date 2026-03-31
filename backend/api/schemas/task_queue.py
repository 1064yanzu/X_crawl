from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from api.schemas.task import CrawlStrategy, TaskOut

QueueStatus = Literal["running", "paused", "completed"]


class TaskQueueItemRequest(BaseModel):
    keyword: str = Field(description="搜索关键词", min_length=1, max_length=200)
    product: Literal["Top", "Latest", "Photos", "Videos"] = Field(default="Top")
    fetch_replies: bool = Field(default=False, description="是否抓取评论回复")
    max_replies_per_tweet: int = Field(default=0, ge=0, description="每条帖子最多抓取的回复数量（0 代表不限）")
    reply_depth: int = Field(default=2, ge=1, le=5, description="评论抓取深度")
    crawl_strategy: CrawlStrategy = Field(default="dfs", description="爬取策略")
    platform: Literal["x", "weibo"] = Field(default="x", description="目标平台")
    start_date: Optional[str] = Field(default=None, description="微博时间范围起始 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="微博时间范围结束 YYYY-MM-DD")


class TaskQueueCreateRequest(BaseModel):
    name: Optional[str] = Field(default=None, description="任务队列名称，可选")
    tasks: list[TaskQueueItemRequest] = Field(min_length=1, max_length=100, description="按顺序执行的任务列表")


class TaskQueueOut(BaseModel):
    queue_id: str
    name: str
    status: QueueStatus
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    current_task_id: Optional[str] = None
    total_tasks: int = 0
    completed_tasks: int = 0
    running_tasks: int = 0
    pending_tasks: int = 0
    failed_tasks: int = 0
    stopped_tasks: int = 0
    tasks: list[TaskOut] = Field(default_factory=list)
