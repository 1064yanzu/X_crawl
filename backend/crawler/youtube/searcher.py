"""
YouTube 爬取任务主入口。

包含两类任务：
- search(...)         关键词搜索（search.list → videos.list → 评论）
- crawl_channel(...)  频道 uploads 抓取（channels.list → playlistItems.list → videos.list → 评论）

统一的执行路径：
1. 收集视频 ID（搜索或频道）
2. 用 video_fetcher 批量补详情
3. 若 fetch_replies=True，逐视频拉评论 + 楼中楼
4. 期间定期上报预览 / 写断点 / 响应暂停停止信号

本文件不直接访问浏览器或账号池——YouTube 完全依赖 HTTP API。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from . import (
    api_client,
    channel_fetcher,
    checkpoint,
    comment_fetcher,
    parser,
    url_parser,
    video_fetcher,
)

logger = logging.getLogger(__name__)


@dataclass
class YouTubeCrawlResult:
    videos: list[dict] = field(default_factory=list)
    resumed: bool = False
    replies_fetched: int = 0
    pages_fetched: int = 0
    quota_exhausted: bool = False


def _noop_signal(_: Optional[str]) -> None:  # pragma: no cover
    return None


def _default_on_progress(_: str, __: Optional[int], ___: list[dict]) -> None:  # pragma: no cover
    return None


def _to_rfc3339(date_str: Optional[str], *, end_of_day: bool = False) -> Optional[str]:
    """
    任务的 start_date / end_date 采用 `YYYY-MM-DD`；YouTube API 需要 RFC3339。
    若已经是 ISO 字符串，原样返回。
    """
    if not date_str:
        return None
    text = str(date_str).strip()
    if not text:
        return None
    if "T" in text:
        return text
    try:
        dt = datetime.strptime(text, "%Y-%m-%d")
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return text


def _fetch_comment_phase(
    videos: list[dict],
    *,
    task_id: Optional[str],
    fetch_replies: bool,
    reply_depth: int,
    max_replies_per_video: int,
    signal_checker: Callable[[Optional[str]], None],
    on_progress: Callable[[str, Optional[int], list[dict]], None],
    state: dict,
    resumed: bool,
) -> tuple[int, bool]:
    """
    为 `videos` 列表中尚未抓评论的视频补充 replies；返回 (本阶段新增评论总数, 是否因配额暂停)。
    """
    if not fetch_replies:
        return 0, False

    completed: set[str] = set(state.get("completed_comment_video_ids") or [])
    total_added = 0
    # 仅统计"待抓"的视频数量用于进度显示（已完成的跳过）
    pending_total = sum(
        1 for v in videos if v.get("id") and v.get("id") not in completed
    )
    pending_done = 0
    for video in videos:
        vid = video.get("id")
        if not vid:
            continue
        if vid in completed:
            continue

        signal_checker(task_id)
        pending_done += 1
        video_title = (video.get("platform_extra") or {}).get("title") or vid
        short_title = video_title if len(video_title) <= 40 else video_title[:37] + "..."
        on_progress(
            f"[YouTube] 评论抓取 {pending_done}/{pending_total}：{short_title} · 正在翻第 1 页...",
            pending_done,
            videos,
        )

        # 为当前视频维护一个实时进度 dict，挂在 platform_extra 上供前端显示
        video.setdefault("platform_extra", {})
        live_stats = {
            "pages_fetched": 0,
            "fetched_top_level_count": 0,
            "fetched_total_count": 0,
            "comments_disabled": False,
            "phase": "running",
        }
        video["platform_extra"]["comment_stats"] = live_stats

        # 节流预览/ phase 更新（避免每页都 persist）
        _last_emit_ts: list[float] = [0.0]

        def _on_page(info: dict) -> None:
            now = time.monotonic()
            live_stats["pages_fetched"] = int(info.get("pages", 0))
            live_stats["fetched_top_level_count"] = int(info.get("top_level_count", 0))
            live_stats["fetched_total_count"] = int(info.get("total_count", 0))
            # 每 ~1 秒或抓完一整页（非楼中楼事件）更新一次 phase
            should_emit = info.get("stage") == "top" or (now - _last_emit_ts[0]) > 1.0
            if not should_emit:
                return
            _last_emit_ts[0] = now
            stage_label = "翻页中" if info.get("has_next") else "本条抓取完成"
            if info.get("stage") == "sub":
                stage_label = f"补楼中楼 +{info.get('sub_fetched_this_thread', 0)}"
            phase_text = (
                f"[YouTube] 评论抓取 {pending_done}/{pending_total}：{short_title} · "
                f"第 {live_stats['pages_fetched']} 页 · "
                f"顶级 {live_stats['fetched_top_level_count']} / 总计 {live_stats['fetched_total_count']} 条 · "
                f"{stage_label}"
            )
            on_progress(phase_text, pending_done, videos)

        try:
            result = comment_fetcher.fetch_comments_for_video(
                vid,
                task_id=task_id,
                max_comments=max_replies_per_video,
                depth=reply_depth,
                signal_checker=signal_checker,
                on_page=_on_page,
            )
        except api_client.YouTubeQuotaExhausted:
            live_stats["phase"] = "quota_exhausted"
            return total_added, True
        except api_client.YouTubeApiError as exc:
            logger.warning("YouTube 视频 %s 评论抓取失败: %s", vid, exc)
            video.setdefault("platform_extra", {})
            video["platform_extra"]["comment_error"] = f"{exc.reason or exc.status}: {exc}"
            live_stats["phase"] = "error"
            completed.add(vid)
            continue

        replies = result.get("replies") or []
        video["replies"] = replies
        video.setdefault("platform_extra", {})
        final_stats = {
            "fetched_top_level_count": result.get("fetched_top_level_count", len(replies)),
            "fetched_total_count": result.get("fetched_total_count", 0),
            "pages_fetched": result.get("pages_fetched", 0),
            "comments_disabled": result.get("disabled", False),
            "phase": "done",
        }
        video["platform_extra"]["comment_stats"] = final_stats
        total_added += int(result.get("fetched_total_count") or 0)
        completed.add(vid)

        # 更新 checkpoint 的进度（按视频维度）
        state["completed_comment_video_ids"] = list(completed)
        pending = [x for x in state.get("pending_comment_video_ids", []) if x not in completed]
        state["pending_comment_video_ids"] = pending
        state["videos"] = videos
        checkpoint.save_checkpoint(task_id, state)
        summary = (
            f"{len(replies)} 条顶级 / {final_stats['fetched_total_count']} 条总计"
            if not final_stats["comments_disabled"]
            else "评论已关闭"
        )
        on_progress(
            f"[YouTube] 评论抓取 {pending_done}/{pending_total} 完成：{short_title} · "
            f"{final_stats['pages_fetched']} 页 · {summary}",
            pending_done,
            videos,
        )
    _ = resumed
    return total_added, False


def _dedup_and_extend(
    existing_ids: list[str],
    existing_videos: list[dict],
    new_tweets: list[dict],
    *,
    exclude_ids: Optional[set[str]] = None,
) -> tuple[list[str], list[dict]]:
    """把 new_tweets 合并到 existing_videos，按 id 去重并跳过 exclude_ids。"""
    seen: set[str] = set(existing_ids)
    blocked: set[str] = set(exclude_ids or [])
    merged_ids = list(existing_ids)
    merged_videos = list(existing_videos)
    for tweet in new_tweets:
        vid = str(tweet.get("id") or "").strip()
        if not vid or vid in seen or vid in blocked:
            continue
        seen.add(vid)
        merged_ids.append(vid)
        merged_videos.append(tweet)
    return merged_ids, merged_videos


# ────────────────────────────────────────────────────────────────────────────
# 关键词搜索入口
# ────────────────────────────────────────────────────────────────────────────


def search(
    *,
    keyword: str,
    task_id: Optional[str] = None,
    resume: bool = True,
    max_videos: int = 50,
    fetch_replies: bool = False,
    reply_depth: int = 1,
    max_replies_per_video: int = 0,
    order: str = "relevance",
    region_code: Optional[str] = None,
    relevance_language: Optional[str] = None,
    video_duration: str = "any",
    video_definition: str = "any",
    type_filter: str = "video",
    published_after: Optional[str] = None,
    published_before: Optional[str] = None,
    signal_checker: Optional[Callable[[Optional[str]], None]] = None,
    on_progress: Optional[Callable[[str, Optional[int], list[dict]], None]] = None,
    exclude_ids: Optional[set[str]] = None,
) -> YouTubeCrawlResult:
    signal_checker = signal_checker or _noop_signal
    on_progress = on_progress or _default_on_progress

    state: dict = {}
    if resume and task_id:
        loaded = checkpoint.load_checkpoint(task_id)
        if checkpoint.same_scope(loaded, mode="keyword_search", keyword=keyword):
            state = loaded
    if not state:
        state = checkpoint.build_state(mode="keyword_search", keyword=keyword)

    resumed = bool(state.get("videos"))
    collected_ids: list[str] = list(state.get("collected_video_ids") or [])
    videos: list[dict] = list(state.get("videos") or [])
    next_page_token: Optional[str] = state.get("search_next_page_token")
    pages_fetched: int = int(state.get("search_pages_fetched") or 0)

    remaining = max_videos - len(collected_ids)
    quota_exhausted = False

    if remaining > 0:
        on_progress("[YouTube] 正在调用搜索接口获取视频列表...", None, videos)
        base_params = {
            "part": "snippet",
            "q": keyword,
            "type": type_filter or "video",
            "maxResults": min(50, max(1, remaining)),
            "order": order or "relevance",
            "safeSearch": "none",
            "videoDuration": video_duration or "any",
            "videoDefinition": video_definition or "any",
        }
        published_after_rfc = _to_rfc3339(published_after)
        published_before_rfc = _to_rfc3339(published_before, end_of_day=True)
        if published_after_rfc:
            base_params["publishedAfter"] = published_after_rfc
        if published_before_rfc:
            base_params["publishedBefore"] = published_before_rfc
        if region_code:
            base_params["regionCode"] = region_code
        if relevance_language:
            base_params["relevanceLanguage"] = relevance_language

        try:
            while remaining > 0:
                signal_checker(task_id)
                params = dict(base_params)
                params["maxResults"] = min(50, max(1, remaining))
                if next_page_token:
                    params["pageToken"] = next_page_token

                payload = api_client.call_list("search.list", params)
                pages_fetched += 1
                items = payload.get("items") or []
                if not items:
                    next_page_token = payload.get("nextPageToken")
                    if not next_page_token:
                        break
                    continue

                lightweight_tweets = []
                for item in items:
                    kind = ((item.get("id") or {}).get("kind") or "")
                    if "video" not in kind and type_filter == "video":
                        continue
                    tweet = parser.video_to_tweet(item)
                    if tweet and tweet.get("id"):
                        lightweight_tweets.append(tweet)

                collected_ids, videos = _dedup_and_extend(
                    collected_ids, videos, lightweight_tweets, exclude_ids=exclude_ids
                )
                on_progress(
                    f"[YouTube] 搜索已累计 {len(videos)} / {max_videos} 个视频",
                    pages_fetched,
                    videos,
                )

                state.update(
                    checkpoint.build_state(
                        mode="keyword_search",
                        keyword=keyword,
                        search_next_page_token=payload.get("nextPageToken"),
                        search_pages_fetched=pages_fetched,
                        collected_video_ids=collected_ids,
                        videos=videos,
                        pending_comment_video_ids=collected_ids if fetch_replies else [],
                        completed_comment_video_ids=state.get("completed_comment_video_ids") or [],
                    )
                )
                checkpoint.save_checkpoint(task_id, state)

                next_page_token = payload.get("nextPageToken")
                remaining = max_videos - len(collected_ids)
                if not next_page_token or remaining <= 0:
                    break
        except api_client.YouTubeQuotaExhausted:
            quota_exhausted = True

    # 补详情阶段
    if videos and not quota_exhausted:
        signal_checker(task_id)
        on_progress(f"[YouTube] 正在补充 {len(videos)} 个视频的详情...", None, videos)
        try:
            details = video_fetcher.fetch_video_details([v["id"] for v in videos])
            for idx, video in enumerate(videos):
                vid = video.get("id")
                if vid and vid in details:
                    videos[idx] = parser.merge_video_detail(video, details[vid])
            state["videos"] = videos
            checkpoint.save_checkpoint(task_id, state)
            on_progress("[YouTube] 视频详情补齐完成", None, videos)
        except api_client.YouTubeQuotaExhausted:
            quota_exhausted = True

    # 评论阶段
    replies_added = 0
    if fetch_replies and not quota_exhausted:
        replies_added, quota_exhausted = _fetch_comment_phase(
            videos,
            task_id=task_id,
            fetch_replies=fetch_replies,
            reply_depth=reply_depth,
            max_replies_per_video=max_replies_per_video,
            signal_checker=signal_checker,
            on_progress=on_progress,
            state=state,
            resumed=resumed,
        )

    return YouTubeCrawlResult(
        videos=videos,
        resumed=resumed,
        replies_fetched=replies_added,
        pages_fetched=pages_fetched,
        quota_exhausted=quota_exhausted,
    )


# ────────────────────────────────────────────────────────────────────────────
# 频道 uploads 采集入口
# ────────────────────────────────────────────────────────────────────────────


def crawl_channel(
    *,
    channel_input: str,
    task_id: Optional[str] = None,
    resume: bool = True,
    max_videos: int = 50,
    fetch_replies: bool = False,
    reply_depth: int = 1,
    max_replies_per_video: int = 0,
    signal_checker: Optional[Callable[[Optional[str]], None]] = None,
    on_progress: Optional[Callable[[str, Optional[int], list[dict]], None]] = None,
    exclude_ids: Optional[set[str]] = None,
) -> YouTubeCrawlResult:
    signal_checker = signal_checker or _noop_signal
    on_progress = on_progress or _default_on_progress

    descriptor = channel_fetcher.normalize_channel_input(channel_input)
    on_progress(f"[YouTube] 解析频道：{descriptor['kind']}={descriptor['value']}", None, [])

    # 断点恢复按解析后的 channel_id 判断更稳定
    preload_state: dict = {}
    if resume and task_id:
        loaded = checkpoint.load_checkpoint(task_id)
        if loaded and str(loaded.get("mode") or "") == "channel_uploads":
            preload_state = loaded  # 先保留，下面解析完 channel_id 再校验

    resolved = channel_fetcher.resolve_uploads_playlist(channel_input)
    channel_id = resolved["channel_id"]
    uploads_playlist_id = resolved["uploads_playlist_id"]

    if preload_state and preload_state.get("channel_id") != channel_id:
        preload_state = {}

    state = preload_state or checkpoint.build_state(
        mode="channel_uploads",
        channel_id=channel_id,
    )

    resumed = bool(state.get("videos"))
    collected_ids: list[str] = list(state.get("collected_video_ids") or [])
    videos: list[dict] = list(state.get("videos") or [])
    next_token: Optional[str] = state.get("search_next_page_token")
    pages_fetched = int(state.get("search_pages_fetched") or 0)

    remaining = max_videos - len(collected_ids)
    quota_exhausted = False
    try:
        if remaining > 0:
            for page_index, video_ids, cursor, _raw in channel_fetcher.iter_playlist_video_ids(
                uploads_playlist_id,
                max_videos=remaining,
                start_page_token=next_token,
            ):
                signal_checker(task_id)
                pages_fetched += 1
                # 立即按页补齐详情：把 videos.list 的完整数据拿到手再入库/预览
                # 这样用户在实时预览里看到的就是真·标题/封面/作者，而不是占位符
                try:
                    details_map = video_fetcher.fetch_video_details(video_ids)
                except api_client.YouTubeQuotaExhausted:
                    quota_exhausted = True
                    break

                detailed_tweets: list[dict] = []
                for vid in video_ids:
                    full = details_map.get(vid)
                    if full:
                        detailed_tweets.append(full)
                    else:
                        # 偶发情况下 videos.list 可能不返回（视频被下架），仍保留 id 占位
                        detailed_tweets.append({
                            "id": vid,
                            "platform": "youtube",
                            "url": f"https://youtu.be/{vid}",
                        })
                collected_ids, videos = _dedup_and_extend(
                    collected_ids, videos, detailed_tweets, exclude_ids=exclude_ids
                )
                on_progress(
                    f"[YouTube] 频道 {resolved.get('channel_title') or channel_id} · 第 {pages_fetched} 页 · 已累计 {len(videos)} / {max_videos} 个视频",
                    pages_fetched,
                    videos,
                )
                next_token = cursor
                state.update(
                    checkpoint.build_state(
                        mode="channel_uploads",
                        channel_id=channel_id,
                        search_next_page_token=cursor,
                        search_pages_fetched=pages_fetched,
                        collected_video_ids=collected_ids,
                        videos=videos,
                        pending_comment_video_ids=collected_ids if fetch_replies else [],
                        completed_comment_video_ids=state.get("completed_comment_video_ids") or [],
                    )
                )
                checkpoint.save_checkpoint(task_id, state)
                if not cursor:
                    break
                if len(collected_ids) >= max_videos:
                    break
    except api_client.YouTubeQuotaExhausted:
        quota_exhausted = True

    # 兜底：对仍缺少 duration 的视频（例如 resume 出来的旧轻量占位）再补一次
    if videos and not quota_exhausted:
        signal_checker(task_id)
        missing_detail_ids = [
            v["id"]
            for v in videos
            if v.get("id") and not (v.get("platform_extra") or {}).get("duration_iso")
        ]
        if missing_detail_ids:
            on_progress(f"[YouTube] 正在补充 {len(missing_detail_ids)} 个视频的详情...", None, videos)
            try:
                details = video_fetcher.fetch_video_details(missing_detail_ids)
                for idx, video in enumerate(videos):
                    vid = video.get("id")
                    if vid and vid in details:
                        videos[idx] = parser.merge_video_detail(video, details[vid])
                state["videos"] = videos
                checkpoint.save_checkpoint(task_id, state)
                on_progress("[YouTube] 视频详情补齐完成", None, videos)
            except api_client.YouTubeQuotaExhausted:
                quota_exhausted = True

    replies_added = 0
    if fetch_replies and not quota_exhausted:
        replies_added, quota_exhausted = _fetch_comment_phase(
            videos,
            task_id=task_id,
            fetch_replies=fetch_replies,
            reply_depth=reply_depth,
            max_replies_per_video=max_replies_per_video,
            signal_checker=signal_checker,
            on_progress=on_progress,
            state=state,
            resumed=resumed,
        )

    return YouTubeCrawlResult(
        videos=videos,
        resumed=resumed,
        replies_fetched=replies_added,
        pages_fetched=pages_fetched,
        quota_exhausted=quota_exhausted,
    )


# ────────────────────────────────────────────────────────────────────────────
# 视频链接批量采集入口（video_urls）
# ────────────────────────────────────────────────────────────────────────────


def crawl_by_video_ids(
    *,
    video_urls: list[str] | str,
    task_id: Optional[str] = None,
    resume: bool = True,
    max_videos: int = 0,
    fetch_replies: bool = False,
    reply_depth: int = 1,
    max_replies_per_video: int = 0,
    signal_checker: Optional[Callable[[Optional[str]], None]] = None,
    on_progress: Optional[Callable[[str, Optional[int], list[dict]], None]] = None,
    exclude_ids: Optional[set[str]] = None,
) -> YouTubeCrawlResult:
    """
    按用户提供的一批视频 URL / ID 采集视频详情（可选评论）。
    - 跳过搜索阶段，直接走 videos.list 补详情
    - 再按需进入评论阶段（复用 _fetch_comment_phase）
    - max_videos > 0 时对去重后的 id 列表截取前 N 个；=0 不限
    """
    signal_checker = signal_checker or _noop_signal
    on_progress = on_progress or _default_on_progress

    parsed_ids, invalid_lines = url_parser.parse_video_ids(video_urls)
    if exclude_ids:
        parsed_ids = [vid for vid in parsed_ids if vid not in exclude_ids]
    if max_videos and max_videos > 0:
        parsed_ids = parsed_ids[:max_videos]

    if not parsed_ids:
        on_progress(
            "[YouTube] 未解析到任何有效的视频 ID，请检查粘贴内容",
            None,
            [],
        )
        return YouTubeCrawlResult(videos=[], resumed=False)

    signature = checkpoint.compute_video_ids_signature(parsed_ids)

    state: dict = {}
    if resume and task_id:
        loaded = checkpoint.load_checkpoint(task_id)
        if checkpoint.same_scope(loaded, mode="video_urls", video_ids_signature=signature):
            state = loaded
    if not state:
        state = checkpoint.build_state(
            mode="video_urls",
            video_ids_signature=signature,
            collected_video_ids=parsed_ids,
        )

    resumed = bool(state.get("videos"))
    existing_videos: list[dict] = list(state.get("videos") or [])
    existing_ids = {v.get("id") for v in existing_videos if v.get("id")}

    merged_videos: list[dict] = list(existing_videos)
    for vid in parsed_ids:
        if vid not in existing_ids:
            merged_videos.append(
                {
                    "id": vid,
                    "platform": "youtube",
                    "url": f"https://www.youtube.com/watch?v={vid}",
                }
            )
            existing_ids.add(vid)

    state["collected_video_ids"] = parsed_ids
    state["videos"] = merged_videos
    checkpoint.save_checkpoint(task_id, state)

    invalid_hint = f"（另有 {len(invalid_lines)} 行无法解析，已忽略）" if invalid_lines else ""
    need_detail_ids = [
        v["id"]
        for v in merged_videos
        if v.get("id") and not (v.get("platform_extra") or {}).get("duration_iso")
    ]
    # 先报告"开始补齐详情"阶段，但暂不把轻量占位推给预览
    on_progress(
        f"[YouTube] 已识别 {len(parsed_ids)} 个视频{invalid_hint}，开始补齐详情 ({len(need_detail_ids)} 条待补)...",
        None,
        [v for v in merged_videos if (v.get("platform_extra") or {}).get("duration_iso")],
    )

    quota_exhausted = False
    try:
        signal_checker(task_id)
        if need_detail_ids:
            details = video_fetcher.fetch_video_details(need_detail_ids)
            for idx, video in enumerate(merged_videos):
                vid = video.get("id")
                if vid and vid in details:
                    merged_videos[idx] = parser.merge_video_detail(video, details[vid])
            state["videos"] = merged_videos
            checkpoint.save_checkpoint(task_id, state)
            on_progress(
                f"[YouTube] 已补齐 {len(details)}/{len(need_detail_ids)} 个视频的详情",
                None,
                merged_videos,
            )
        else:
            on_progress("[YouTube] 视频详情均已就绪", None, merged_videos)
    except api_client.YouTubeQuotaExhausted:
        quota_exhausted = True

    replies_added = 0
    if fetch_replies and not quota_exhausted:
        state.setdefault("pending_comment_video_ids", list(parsed_ids))
        replies_added, quota_exhausted = _fetch_comment_phase(
            merged_videos,
            task_id=task_id,
            fetch_replies=fetch_replies,
            reply_depth=reply_depth,
            max_replies_per_video=max_replies_per_video,
            signal_checker=signal_checker,
            on_progress=on_progress,
            state=state,
            resumed=resumed,
        )

    return YouTubeCrawlResult(
        videos=merged_videos,
        resumed=resumed,
        replies_fetched=replies_added,
        pages_fetched=0,
        quota_exhausted=quota_exhausted,
    )

