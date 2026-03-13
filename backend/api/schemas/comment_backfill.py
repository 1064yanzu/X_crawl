from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from api.schemas.task import TaskOut


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
