"""
任务数据模型（v3 - 含回复抓取和爬取策略支持）
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal

TaskStatus = Literal["pending", "running", "done", "failed", "paused", "stopped"]
CrawlStrategy = Literal["bfs", "dfs"]
RiskState = Literal["none", "challenge", "rate_limited", "login_required"]
QualityState = Literal["complete", "partial", "interrupted"]


class SearchRequest(BaseModel):
    keyword: str = Field(description="搜索关键词", min_length=1, max_length=200)
    max_count: int = Field(default=0, ge=0, description="最多获取的推文数量（0 表示不限制）")
    product: Literal["Top", "Latest", "Photos", "Videos"] = Field(default="Top")
    resume: bool = Field(default=True, description="是否从断点继续（若有检查点）")
    task_id: Optional[str] = Field(default=None, description="若指定，复用该 task_id 断点继续爬取")
    # ── 回复抓取 ──
    fetch_replies: bool = Field(default=False, description="是否抓取每条推文的回复评论")
    max_replies_per_tweet: int = Field(
        default=0,
        description="每条推文最多抓取的回复数量（0代表无限制，fetch_replies=true 时生效）"
    )
    reply_depth: int = Field(
        default=2, ge=1, le=5,
        description="评论抓取深度（1=仅一级评论，2=含二级评论，依此类推）"
    )
    crawl_strategy: CrawlStrategy = Field(
        default="dfs",
        description=(
            "爬取策略：\n"
            "- bfs（广度优先）：先爬完所有搜索页的推文，再统一抓取所有推文的回复\n"
            "- dfs（深度优先）：每爬到一条推文，立即抓取其回复，再继续翻页"
        )
    )


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
    risk_state: RiskState = Field(default="none", description="风险状态：none/challenge/rate_limited/login_required")
    quality_state: QualityState = Field(default="complete", description="任务质量：complete/partial/interrupted")
    runtime_metrics: dict = Field(default_factory=dict, description="任务运行期指标汇总")
    live_metrics: dict = Field(default_factory=dict, description="实时遥测指标（SSE/摘要模式可用）")
    time_coverage: dict = Field(default_factory=dict, description="推文/评论时间覆盖范围统计")
    latest_action: Optional[dict] = Field(default=None, description="最近一次结构化动作事件")
    queue_position: Optional[int] = Field(default=None, description="队列位置（pending 时有效）")
    last_event_at: Optional[str] = Field(default=None, description="最近状态事件时间（ISO）")
    resumed: bool = Field(default=False, description="是否从断点恢复")
    # ── 回复相关字段 ──
    fetch_replies: bool = Field(default=False)
    crawl_strategy: CrawlStrategy = Field(default="bfs")
    max_replies_per_tweet: int = Field(default=20)
    reply_depth: int = Field(default=2, description="评论抓取深度")
    replies_fetched: int = Field(default=0, description="已抓取的总回复数")
    # ── 推文数据 ──
    tweets: list[dict] = Field(default_factory=list)
    # ── 实时预览（最多 crawler_preview_count 条，避免前端性能问题）──
    preview_tweets: list[dict] = Field(default_factory=list)
    # ── 爬虫实时阶段状态（空字符串代表尚未开始）──
    crawl_phase: str = Field(default="", description="爬虫当前阶段描述，如 '等待第 1 页数据'")
    debug_screenshot: Optional[str] = Field(default=None, description="错误诊断截图 URL")
