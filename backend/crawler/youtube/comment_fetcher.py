"""
YouTube 评论 + 楼中楼抓取。

主要接口：
- fetch_comments_for_video(video_id, task_id, *, max_comments, depth, on_progress=None) -> list[reply_dict]

策略：
- commentThreads.list(part=snippet,replies, videoId=..., maxResults=100, order="time")
- 遇到 `commentsDisabled` 状态（403.commentsDisabled）时安静返回 []
- 若 depth > 1，对 `totalReplyCount > len(embedded.comments)` 的线程另调
  `comments.list(parentId=top_level_comment_id)` 拉全二级评论
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from . import api_client, parser

logger = logging.getLogger(__name__)


DEFAULT_PAGE_SIZE = 100  # 官方上限 100


def fetch_comments_for_video(
    video_id: str,
    *,
    task_id: Optional[str] = None,
    max_comments: int = 0,
    depth: int = 1,
    order: str = "time",
    signal_checker: Optional[Callable[[Optional[str]], None]] = None,
    on_page: Optional[Callable[[dict], None]] = None,
) -> dict:
    """
    抓取单个视频的评论树。

    :param max_comments: 顶层评论上限（含楼中楼，0 表示无限制）
    :param depth: 1=仅顶层；2=含二级；>2 时仍按 depth=2 处理（YouTube 评论最多二层）
    :param signal_checker: 可选的暂停/停止信号检查（每页调用一次）
    :param on_page: 可选的分页进度回调。每抓完一页顶层评论、或抓完某条顶层评论的楼中楼时触发。
        回调参数为字典，包含：
          - stage: "top" | "sub"            本次事件类型
          - pages: int                       已抓取的顶层评论页数
          - top_level_count: int             已落盘的顶层评论数
          - total_count: int                 已落盘的评论总数（顶层 + 楼中楼）
          - video_id: str
          - has_next: bool                   顶层评论是否还有下一页
          - current_thread_id: Optional[str] 当前正在处理/刚完成的顶层评论 id（仅 stage=sub）
          - sub_fetched_this_thread: Optional[int] 本次抓取楼中楼的累计条数（仅 stage=sub）
    :return: {
        "replies": [reply_dict],
        "fetched_top_level_count": int,
        "fetched_total_count": int,
        "pages_fetched": int,
        "disabled": bool,  # 频道/视频关闭了评论
    }
    """
    if not video_id:
        return {"replies": [], "fetched_top_level_count": 0, "fetched_total_count": 0, "pages_fetched": 0, "disabled": False}

    want_replies = int(depth or 1) > 1

    replies: list[dict] = []
    total_count = 0
    pages = 0
    next_token: Optional[str] = None

    def _emit_page(*, has_next: bool, stage: str = "top", thread_id: Optional[str] = None, sub_count: Optional[int] = None) -> None:
        if on_page is None:
            return
        try:
            on_page({
                "stage": stage,
                "pages": pages,
                "top_level_count": len(replies),
                "total_count": total_count,
                "video_id": video_id,
                "has_next": has_next,
                "current_thread_id": thread_id,
                "sub_fetched_this_thread": sub_count,
            })
        except Exception:
            logger.debug("comment on_page 回调异常", exc_info=True)

    try:
        while True:
            if signal_checker:
                signal_checker(task_id)

            params: dict = {
                "part": "snippet,replies" if want_replies else "snippet",
                "videoId": video_id,
                "maxResults": DEFAULT_PAGE_SIZE,
                "order": order,
                "textFormat": "plainText",
            }
            if next_token:
                params["pageToken"] = next_token

            try:
                payload = api_client.call_list("commentThreads.list", params)
            except api_client.YouTubeApiError as exc:
                if exc.reason == "commentsDisabled":
                    logger.info("视频 %s 评论已关闭，跳过", video_id)
                    _emit_page(has_next=False)
                    return {
                        "replies": replies,
                        "fetched_top_level_count": len(replies),
                        "fetched_total_count": total_count,
                        "pages_fetched": pages,
                        "disabled": True,
                    }
                if exc.reason == "videoNotFound":
                    logger.info("视频 %s 已不可访问，跳过评论", video_id)
                    _emit_page(has_next=False)
                    return {
                        "replies": replies,
                        "fetched_top_level_count": len(replies),
                        "fetched_total_count": total_count,
                        "pages_fetched": pages,
                        "disabled": True,
                    }
                raise

            pages += 1
            items = payload.get("items") or []
            for thread in items:
                reply = parser.comment_thread_to_reply(thread)
                total_reply_count = int(((thread.get("snippet") or {}).get("totalReplyCount") or 0))
                embedded = reply.get("replies") or []

                # 若 depth 要求二级且还有未展示的楼中楼，则补拉
                if want_replies and total_reply_count > len(embedded):
                    top_id = reply.get("id")
                    if top_id:
                        sub_fetched_running = 0

                        def _on_sub_page(count: int, *, top_id_local: str = top_id) -> None:
                            nonlocal sub_fetched_running
                            sub_fetched_running = count
                            _emit_page(
                                has_next=bool(next_token) or bool(payload.get("nextPageToken")),
                                stage="sub",
                                thread_id=top_id_local,
                                sub_count=count,
                            )

                        try:
                            full = _fetch_all_sub_comments(
                                top_id,
                                already_loaded=len(embedded),
                                task_id=task_id,
                                signal_checker=signal_checker,
                                on_sub_page=_on_sub_page,
                            )
                            if full:
                                reply["replies"] = full
                        except api_client.YouTubeApiError as exc:
                            logger.warning(
                                "拉取楼中楼失败 video=%s comment=%s: %s",
                                video_id,
                                top_id,
                                exc,
                            )

                replies.append(reply)
                total_count += 1 + len(reply.get("replies") or [])

                if max_comments and len(replies) >= int(max_comments):
                    _emit_page(has_next=False)
                    return {
                        "replies": replies,
                        "fetched_top_level_count": len(replies),
                        "fetched_total_count": total_count,
                        "pages_fetched": pages,
                        "disabled": False,
                    }

            next_token = payload.get("nextPageToken")
            _emit_page(has_next=bool(next_token))
            if not next_token:
                break
    except api_client.YouTubeApiError:
        raise

    return {
        "replies": replies,
        "fetched_top_level_count": len(replies),
        "fetched_total_count": total_count,
        "pages_fetched": pages,
        "disabled": False,
    }


def _fetch_all_sub_comments(
    parent_id: str,
    *,
    already_loaded: int = 0,
    task_id: Optional[str] = None,
    signal_checker: Optional[Callable[[Optional[str]], None]] = None,
    on_sub_page: Optional[Callable[[int], None]] = None,
) -> list[dict]:
    """按 parentId 分页取所有二级评论，合并为 reply dict 列表。"""
    collected: list[dict] = []
    next_token: Optional[str] = None
    while True:
        if signal_checker:
            signal_checker(task_id)
        params: dict = {
            "part": "snippet",
            "parentId": parent_id,
            "maxResults": DEFAULT_PAGE_SIZE,
            "textFormat": "plainText",
        }
        if next_token:
            params["pageToken"] = next_token

        payload = api_client.call_list("comments.list", params)
        for comment in payload.get("items") or []:
            collected.append(parser.comment_resource_to_reply(comment))

        if on_sub_page is not None:
            try:
                on_sub_page(len(collected))
            except Exception:
                logger.debug("on_sub_page 回调异常", exc_info=True)

        next_token = payload.get("nextPageToken")
        if not next_token:
            break
    # 若 commentThreads.replies 已有部分数据，这里是完整列表，直接替换即可
    _ = already_loaded
    return collected
