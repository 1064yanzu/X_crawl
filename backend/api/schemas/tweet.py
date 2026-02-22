"""
推文数据模型（完整版）
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from api.schemas.user import UserOut


class TweetMetrics(BaseModel):
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quotes: int = 0
    bookmarks: int = 0
    views: Optional[int] = None
    views_state: Optional[str] = None


class VideoVariant(BaseModel):
    bitrate: Optional[int] = None
    content_type: str = ""
    url: str = ""


class MediaSize(BaseModel):
    w: Optional[int] = None
    h: Optional[int] = None
    resize: Optional[str] = None


class VideoInfo(BaseModel):
    aspect_ratio: list[int] = Field(default_factory=list)
    duration_ms: Optional[int] = None
    duration_sec: Optional[float] = None


class MediaItem(BaseModel):
    id: str = ""
    media_key: str = ""
    type: str = Field(description="photo / video / animated_gif")
    url: str = ""
    display_url: str = ""
    expanded_url: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    alt_text: Optional[str] = None
    sensitive: bool = False
    sizes: dict[str, MediaSize] = Field(default_factory=dict)
    video_info: Optional[VideoInfo] = None
    video_variants: list[VideoVariant] = Field(default_factory=list)
    video_url: Optional[str] = Field(default=None, description="最优 MP4 URL")
    video_bitrate: Optional[int] = None
    hls_url: Optional[str] = Field(default=None, description="HLS 流 URL")


class UrlEntity(BaseModel):
    url: Optional[str] = None
    expanded_url: Optional[str] = None
    display_url: Optional[str] = None
    title: Optional[str] = None


class UserMention(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    screen_name: Optional[str] = None


class ReplyTo(BaseModel):
    tweet_id: Optional[str] = None
    user_id: Optional[str] = None
    screen_name: Optional[str] = None


class EditInfo(BaseModel):
    is_edit_eligible: bool = False
    edits_remaining: Optional[int] = None
    editable_until: Optional[str] = None


class TextHighlight(BaseModel):
    start: Optional[int] = None
    end: Optional[int] = None


class TweetOut(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    # ── 基础 ──
    id: str
    conversation_id: str = ""
    text: str
    display_text_range: Optional[list[int]] = None
    created_at: str
    lang: str = ""
    url: str = ""
    source: str = Field(default="", description="发推客户端（如 Twitter Web App）")
    possibly_sensitive: bool = False
    is_translatable: bool = False
    # ── 回复 ──
    reply_to: Optional[ReplyTo] = None
    # ── 互动 ──
    metrics: TweetMetrics = Field(default_factory=TweetMetrics)
    # ── 作者（运行时为 UserOut，序列化为 dict）──
    author: Optional[dict] = None
    # ── 媒体 ──
    media: list[MediaItem] = Field(default_factory=list)
    # ── 文本实体 ──
    hashtags: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    urls: list[UrlEntity] = Field(default_factory=list)
    user_mentions: list[UserMention] = Field(default_factory=list)
    # ── 推文类型 ──
    is_retweet: bool = False
    is_quote: bool = False
    # ── 关联推文（递归，序列化为 dict 避免循环引用问题）──
    quoted_tweet: Optional[dict] = None
    retweeted_tweet: Optional[dict] = None
    # ── 可编辑性 ──
    edit_info: Optional[EditInfo] = None
    # ── 关键词高亮 ──
    text_highlights: list[TextHighlight] = Field(default_factory=list)
    # ── 回复（评论）列表 ──
    replies: list[dict] = Field(
        default_factory=list,
        description="该推文下抓取到的回复列表（每个元素本身也是推文结构，含 thread_context）"
    )
    # ── 线程上下文（当作为回复出现时） ──
    thread_context: Optional[dict] = Field(
        default=None,
        description="当该推文是回复时，包含其所在对话串的上下文信息"
    )
    thread_more_cursor: Optional[str] = Field(
        default=None,
        description="展开更多同串回复的 cursor（若该串回复未完全展示）"
    )

