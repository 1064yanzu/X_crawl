"""
微博数据模型，字段尽可能全面，兼容 X 推文前端展示结构。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WeiboComment:
    """微博评论（一级评论 + 子评论）"""

    id: str
    text: str                                   # 纯文本（已清理 HTML）
    author_name: str
    author_id: str
    created_at: str
    likes: int = 0
    source: str = ""                            # IP 属地 / 来源（如 "来自四川"）
    avatar_url: str = ""                        # 头像
    is_author: bool = False                     # 是否博主
    verified: bool = False                      # 是否认证用户
    verified_reason: str = ""                   # 认证原因
    gender: str = ""                            # f/m
    location: str = ""                          # 所在地
    followers_count: int = 0                    # 粉丝数
    reply_to_user: str = ""                     # 回复的目标用户名
    sub_comments: list = field(default_factory=list)  # 子评论（楼中楼）
    sub_comments_count: int = 0                 # 子评论总数
    platform: str = "weibo"

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "text": self.text,
            "author": {
                "id": self.author_id,
                "name": self.author_name,
                "screen_name": self.author_name,
                "avatar_url": self.avatar_url,
                "profile_url": f"https://weibo.com/u/{self.author_id}",
                "verified": self.verified,
                "verified_reason": self.verified_reason,
                "gender": self.gender,
                "location": self.location,
                "followers_count": self.followers_count,
            },
            "created_at": self.created_at,
            "source": self.source,
            "is_author": self.is_author,
            "metrics": {
                "likes": self.likes,
            },
            "platform": "weibo",
        }
        if self.reply_to_user:
            result["reply_to"] = {"screen_name": self.reply_to_user}
        if self.sub_comments:
            result["replies"] = [c.to_dict() for c in self.sub_comments]
            result["sub_comments_count"] = self.sub_comments_count
        return result


@dataclass
class WeiboPost:
    """微博帖子"""

    mid: str
    text: str
    author_id: str
    author_name: str
    author_avatar: str
    created_at: str
    reposts_count: int = 0
    comments_count: int = 0
    likes_count: int = 0
    source: str = ""                            # 来源设备（如 "微博网页版"）
    verified: bool = False                      # 是否认证用户
    verified_type: str = ""                     # blue/yellow/none
    is_repost: bool = False                     # 是否转发微博
    repost_text: str = ""                       # 原微博正文
    repost_author: str = ""                     # 原微博作者
    repost_reposts: int = 0                     # 原微博转发数
    repost_comments: int = 0                    # 原微博评论数
    repost_likes: int = 0                       # 原微博点赞数
    hashtags: list = field(default_factory=list)   # 话题标签
    platform: str = "weibo"
    url: str = ""
    comments: list = field(default_factory=list)
    comment_stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result: dict = {
            "id": self.mid,
            "text": self.text,
            "platform": "weibo",
            "author": {
                "id": self.author_id,
                "name": self.author_name,
                "screen_name": self.author_name,
                "avatar_url": self.author_avatar,
                "profile_url": f"https://weibo.com/u/{self.author_id}",
                "verified": self.verified,
                "verified_type": self.verified_type,
            },
            "created_at": self.created_at,
            "url": self.url,
            "source": self.source,
            "metrics": {
                "likes": self.likes_count,
                "retweets": self.reposts_count,
                "replies": self.comments_count,
            },
            "replies": [c.to_dict() for c in self.comments],
        }
        if self.comment_stats:
            result["comment_stats"] = self.comment_stats
        if self.hashtags:
            result["hashtags"] = self.hashtags
        if self.is_repost:
            result["quoted_tweet"] = {
                "text": self.repost_text,
                "author": {
                    "name": self.repost_author,
                    "screen_name": self.repost_author,
                },
                "metrics": {
                    "likes": self.repost_likes,
                    "retweets": self.repost_reposts,
                    "replies": self.repost_comments,
                },
            }
        return result


@dataclass
class WeiboCommentFetchResult:
    comments: list[WeiboComment] = field(default_factory=list)
    fetched_total_count: int = 0
    fetched_top_level_count: int = 0
    api_claimed_total: int = 0
    sub_comment_completion_status: str = "top_level_only"
    truncated_reason: Optional[str] = None
    pages_fetched: int = 0
