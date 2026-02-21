"""
任务数据模型（含断点续爬支持）
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal

TaskStatus = Literal["pending", "running", "done", "failed", "paused"]


class SearchRequest(BaseModel):
    keyword: str = Field(description="搜索关键词", min_length=1, max_length=200)
    max_count: int = Field(default=20, ge=1, le=500)
    product: Literal["Top", "Latest", "Photos", "Videos"] = Field(default="Top")
    resume: bool = Field(default=True, description="是否从断点继续（若有检查点）")
    task_id: Optional[str] = Field(default=None, description="若指定，复用该 task_id 断点继续爬取")


class CheckpointInfo(BaseModel):
    task_id: str
    keyword: str
    product: str
    tweets_count: int
    page_fetched: int
    saved_at: str
    can_resume: bool


class TaskOut(BaseModel):
    task_id: str
    status: TaskStatus
    keyword: str
    product: str
    max_count: int
    result_count: int = 0
    current_page: int = Field(default=0, description="当前已爬取页数（实时进度）")
    created_at: str
    finished_at: Optional[str] = None
    error: Optional[str] = None
    resumed: bool = Field(default=False, description="是否从断点恢复")
    tweets: list[dict] = Field(default_factory=list)
