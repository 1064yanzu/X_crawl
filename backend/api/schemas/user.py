"""
用户数据模型（完整版）
"""
from pydantic import BaseModel, Field
from typing import Optional


class DescriptionUrl(BaseModel):
    url: Optional[str] = None
    expanded_url: Optional[str] = None
    display_url: Optional[str] = None


class UserOut(BaseModel):
    # ── 基础 ──
    id: str = Field(description="用户 ID")
    name: str = Field(description="显示名称")
    screen_name: str = Field(description="用户名（@handle）")
    description: str = Field(default="", description="个人简介")
    description_language: str = Field(default="", description="简介语言代码")
    # ── 图像 ──
    avatar_url: str = Field(default="", description="头像 URL（原始尺寸）")
    banner_url: str = Field(default="", description="主页横幅 URL")
    profile_image_shape: str = Field(default="", description="头像形状（Circle/Square）")
    # ── 位置 ──
    location: str = Field(default="", description="位置")
    # ── 主页链接 ──
    website_url: Optional[str] = Field(default=None, description="个人主页链接（完整 URL）")
    website_display: Optional[str] = Field(default=None, description="个人主页链接（显示文本）")
    # ── 统计 ──
    followers_count: int = Field(default=0)
    following_count: int = Field(default=0)
    tweets_count: int = Field(default=0)
    likes_count: int = Field(default=0)
    media_count: int = Field(default=0)
    listed_count: int = Field(default=0)
    # ── 认证 ──
    verified: bool = Field(default=False, description="官方认证")
    verified_type: Optional[str] = Field(default=None, description="认证类型")
    is_blue_verified: bool = Field(default=False, description="Twitter Blue 蓝勾")
    # ── 账号属性 ──
    created_at: str = Field(default="", description="账号创建时间（ISO 8601）")
    is_protected: bool = Field(default=False, description="是否私密账号")
    is_translator: bool = Field(default=False)
    has_custom_timelines: bool = Field(default=False)
    pinned_tweet_ids: list[str] = Field(default_factory=list)
    # ── description 实体 ──
    description_urls: list[DescriptionUrl] = Field(default_factory=list)
    description_mentions: list[dict] = Field(default_factory=list)
