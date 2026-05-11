from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from api.schemas.task import TaskOut
from api.schemas.task_queue import TaskQueueOut


class CommentBackfillProgress(BaseModel):
    total_posts: int = Field(default=0, description="导入文件中去重后的原帖总数")
    eligible_posts: int = Field(default=0, description="符合评论补采条件的帖子数")
    processed_posts: int = Field(default=0, description="已处理的帖子数")
    skipped_posts: int = Field(default=0, description="初始化或运行中跳过的帖子数")
    succeeded_posts: int = Field(default=0, description="已成功处理的帖子数")
    failed_posts: int = Field(default=0, description="处理失败的帖子数")


class CommentBackfillAnalyzeResponse(BaseModel):
    file_name: str
    platform: Literal["x", "weibo"]
    total_rows: int
    original_post_rows: int
    unique_post_count: int
    eligible_posts: int
    skipped_non_post_rows: int
    skipped_zero_comment_posts: int
    skipped_invalid_posts: int
    deduplicated_posts: int
    has_platform_column: bool = False
    detected_platform: Optional[Literal["x", "weibo"]] = None


class CommentBackfillImportResponse(BaseModel):
    task: TaskOut
    summary: CommentBackfillAnalyzeResponse


class CommentBackfillFromTasksRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=100, description="要发起评论补采的已完成任务 ID 列表")
    reply_depth: int = Field(default=2, ge=1, le=5, description="仅 X 生效，评论补采深度")
    max_replies_per_tweet: int = Field(default=0, ge=0, description="每条帖子补采评论上限，0 表示不限")
    queue_name: Optional[str] = Field(default=None, description="批量补采时可选的队列名称")


class CommentBackfillTaskSourceSummary(BaseModel):
    source_task_id: str
    source_keyword: str
    platform: Literal["x", "weibo", "youtube"]
    task_status: str
    result_count: int
    unique_post_count: int
    eligible_posts: int
    skipped_zero_comment_posts: int = 0
    skipped_invalid_posts: int = 0
    skipped_existing_comment_posts: int = 0
    deduplicated_posts: int = 0
    status: Literal["created", "skipped"] = "created"
    reason: Optional[str] = None
    created_task_id: Optional[str] = None


class CommentBackfillFromTasksResponse(BaseModel):
    created_count: int = 0
    queued: bool = False
    queue: Optional[TaskQueueOut] = None
    tasks: list[TaskOut] = Field(default_factory=list)
    sources: list[CommentBackfillTaskSourceSummary] = Field(default_factory=list)
