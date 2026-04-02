"""
微博评论抓取器（v6 - 首页网络拦截 + Python requests 翻页）。

核心机制：
1. 新开标签页 → 访问帖子页面 → tab.listen 拦截首批评论（浏览器自然行为）
2. 从 tab 提取 Cookie 和 XSRF-TOKEN
3. 后续翻页：Python requests 直接请求 buildComments API
4. 关闭标签页

关键发现（v3→v6 调试过程中确认）：
- API 的 total_number 包含**所有层级**的评论（顶层 + 子评论 + 子子评论）
- data 数组只包含顶层评论，每条内嵌部分子评论（comments 字段）
- 一个 total=448 的帖子，顶层评论可能只有 20-30 条
- 子评论需要通过 comments 字段获取（API 内嵌的）
- flow=0（按热度）和 flow=1（按时间）返回的顶层评论数量基本一致
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Optional

import requests as http_requests

from .comment_stats import build_comment_stats, collect_comment_tree_stats
from .models import WeiboComment, WeiboCommentFetchResult

logger = logging.getLogger(__name__)

# 评论 API URL 匹配模式（DrissionPage listen 使用）
COMMENT_API_PATTERN = "ajax/statuses/buildComments"

# API 基础 URL
COMMENT_API_BASE = "https://weibo.com/ajax/statuses/buildComments"

# 网络拦截等待超时
_FIRST_PACKET_TIMEOUT = 20.0
_PACKET_TIMEOUT = 15.0

# 连续无新顶层评论最大容忍次数
_MAX_EMPTY_PAGES = 3


# ────────────────────────────────────────────────────────────
#  URL / Cookie / 请求头 工具函数
# ────────────────────────────────────────────────────────────

def _build_post_url(author_uid: str, post_url: str, mid: str) -> str:
    """构建微博帖子页面 URL。"""
    if post_url and post_url.startswith("http"):
        return post_url
    if author_uid:
        return f"https://weibo.com/{author_uid}/{mid}"
    return f"https://weibo.com/detail/{mid}"


def _build_comment_api_url(
    mid: str, max_id: int = 0, uid: str = "", flow: int = 0
) -> str:
    """构建评论 API URL（参数顺序对照抓包还原）。"""
    params = [
        f"flow={flow}",
        "is_reload=1",
        f"id={mid}",
        "is_show_bulletin=2",
        "is_mix=0",
    ]
    if max_id:
        params.append(f"max_id={max_id}")
    params.append("count=20")
    if uid:
        params.append(f"uid={uid}")
    params.extend([
        "fetch_level=0",
        "locale=zh-CN",
    ])
    return f"{COMMENT_API_BASE}?{'&'.join(params)}"


def _extract_cookies_dict(tab) -> dict[str, str]:
    """从浏览器 tab 提取所有 Cookie 为 {name: value} 字典。"""
    result = {}
    try:
        cookies = tab.cookies()
        if isinstance(cookies, list):
            for c in cookies:
                if isinstance(c, dict):
                    name = c.get("name", "")
                    value = c.get("value", "")
                    if name:
                        result[name] = value
        elif isinstance(cookies, dict):
            result = cookies
    except Exception as e:
        logger.warning(f"提取 Cookie 失败: {e}")
    return result


def _get_xsrf_token(cookies_dict: dict[str, str]) -> str:
    """从 Cookie 字典中提取 XSRF-TOKEN。"""
    return cookies_dict.get("XSRF-TOKEN", "")


def _build_api_headers(xsrf_token: str, referer: str) -> dict[str, str]:
    """构建完整的 API 请求头（对照抓包还原）。"""
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "X-XSRF-TOKEN": xsrf_token,
        "client-version": "3.0.0",
        "server-version": "v2026.03.02.1",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
    }


# ────────────────────────────────────────────────────────────
#  首页网络拦截辅助函数
# ────────────────────────────────────────────────────────────

def _scroll_for_comments(tab, *, task_id: Optional[str] = None) -> None:
    """模拟人类向下滚动浏览评论区（仅首页加载阶段使用）。"""
    from crawler.utils import interruptible_sleep

    steps = random.randint(3, 5)
    for i in range(steps):
        px = random.randint(200, 500)
        try:
            tab.scroll.down(px)
        except Exception:
            try:
                tab.run_js(f"window.scrollBy(0, {px});")
            except Exception:
                pass

        if random.random() < 0.25:
            interruptible_sleep(random.uniform(1.0, 2.5), task_id=task_id)
        else:
            interruptible_sleep(random.uniform(0.3, 0.8), task_id=task_id)

        if i < steps - 1 and random.random() < 0.15:
            up_px = random.randint(50, 150)
            try:
                tab.scroll.up(up_px)
            except Exception:
                try:
                    tab.run_js(f"window.scrollBy(0, -{up_px});")
                except Exception:
                    pass
            interruptible_sleep(random.uniform(0.2, 0.5), task_id=task_id)

    try:
        tab.scroll.to_bottom()
    except Exception:
        try:
            tab.run_js("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass


def _wait_comment_packet(tab, timeout: float = _PACKET_TIMEOUT):
    """等待一个 buildComments API 响应数据包。"""
    try:
        packet = tab.listen.wait(timeout=timeout, raise_err=False)
        if packet:
            return packet
    except Exception as e:
        logger.debug(f"评论数据包等待异常: {e}")
    return None


def _open_post_page_with_retry(
    tab,
    *,
    page_url: str,
    task_id: Optional[str],
    phase_callback=None,
) -> bool:
    """打开微博帖子详情页，命中浏览器 HTTP 418 错误页时执行长冷却后重试。"""
    from config import settings
    from crawler.utils import interruptible_sleep
    from .http_418_guard import detect_weibo_http_418, wait_weibo_http_418_cooldown

    max_attempts = 3
    for attempt in range(max_attempts):
        tab.get(page_url, timeout=20)
        interruptible_sleep(random.uniform(2.0, 3.5), task_id=task_id)
        if not detect_weibo_http_418(tab):
            return True
        if attempt >= max_attempts - 1:
            return False
        wait_weibo_http_418_cooldown(
            task_id=task_id,
            cooldown_seconds=float(
                getattr(settings, "weibo_http_418_cooldown_seconds", 600.0)
            ),
            context="评论页",
            phase_callback=phase_callback,
        )
    return False


def _parse_packet_body(packet) -> Optional[dict]:
    """从拦截到的数据包中提取 JSON body。"""
    try:
        body = packet.response.body
        if isinstance(body, dict):
            return body
        if isinstance(body, str):
            return json.loads(body)
    except Exception as e:
        logger.debug(f"评论数据包解析异常: {e}")
    return None


# ────────────────────────────────────────────────────────────
#  Python requests 翻页
# ────────────────────────────────────────────────────────────

def _requests_fetch_page(
    session: http_requests.Session,
    api_url: str,
    headers: dict[str, str],
) -> Optional[dict]:
    """
    用 Python requests 请求一页评论。

    Returns:
        解析后的 JSON dict，或 None（请求/解析失败）
    """
    try:
        resp = session.get(api_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.warning(
                f"评论 API 返回 HTTP {resp.status_code}，"
                f"URL={api_url[:80]}..."
            )
            return None
        data = resp.json()
        return data
    except http_requests.RequestException as e:
        logger.warning(f"评论 API 请求异常: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"评论 API JSON 解析失败: {e}")
        return None


# ────────────────────────────────────────────────────────────
#  评论计数辅助
# ────────────────────────────────────────────────────────────

def _count_all_comments(comments: list[WeiboComment]) -> int:
    """递归统计所有评论数（含子评论）。"""
    total = len(comments)
    for c in comments:
        total += _count_all_comments(c.sub_comments)
    return total


def _parse_and_collect(
    page_data: list[dict],
    seen_ids: set[str],
    comments: list[WeiboComment],
) -> tuple[int, int]:
    """
    解析一页的评论数据，去重后追加到 comments 列表。

    Returns:
        (新增顶层评论数, 新增总评论数（含子评论）)
    """
    new_top = 0
    new_total = 0

    for c in page_data:
        comment_id = str(c.get("id", ""))
        if comment_id and comment_id in seen_ids:
            continue
        if comment_id:
            seen_ids.add(comment_id)

        parsed = _parse_comment(c)
        comments.append(parsed)
        new_top += 1
        # 该条评论本身 + 内嵌子评论
        new_total += 1 + len(parsed.sub_comments)

    return new_top, new_total


# ────────────────────────────────────────────────────────────
#  主入口
# ────────────────────────────────────────────────────────────

def fetch_comments(
    mid: str,
    author_uid: str = "",
    post_url: str = "",
    post_comment_count: int = 0,
    max_comments: int = 500,
    page_interval: float = 4.0,
    task_id: str | None = None,
    browser_instance=None,
) -> WeiboCommentFetchResult:
    """
    抓取微博评论（v6 - 首页网络拦截 + Python requests 翻页）。

    注意：API 的 total_number 包含所有层级评论（顶层+子评论），
    而 data 数组只返回顶层评论。每条顶层评论的 comments 字段
    内嵌了部分子评论。因此实际获取的评论数可能远小于 total_number，
    这是 API 的正常行为。

    Args:
        mid:            微博帖子 ID
        author_uid:     作者 UID
        post_url:       帖子页面 URL（优先使用）
        max_comments:   最大评论抓取数量（含子评论）
        page_interval:  分页间隔（秒）
        task_id:        任务 ID
    """
    from crawler.browser import get_new_tab
    from crawler.utils import jittered_sleep, check_signal, interruptible_sleep

    comments: list[WeiboComment] = []
    seen_ids: set[str] = set()
    empty_page_count = 0
    all_raw_data: list[dict] = []  # 保留原始数据，子评论补全后重新解析
    session: http_requests.Session | None = None
    api_headers: dict[str, str] = {}
    pages_fetched = 0
    truncated_reason: str | None = None
    sub_comment_completion_status = "top_level_only"
    total_number = 0

    page_url = _build_post_url(author_uid, post_url, mid)
    logger.info(f"评论抓取：打开帖子页面 URL={page_url} (mid={mid})")

    # 前端进度推送
    _update_phase = None
    if task_id:
        try:
            from api.services.task_manager import update_task_phase
            _update_phase = lambda msg: update_task_phase(task_id, msg)
        except ImportError:
            pass

    if _update_phase:
        _update_phase(f"正在打开帖子页面获取评论...")

    tab = browser_instance.new_tab() if browser_instance is not None else get_new_tab()

    try:
        # ─── 阶段 1：访问帖子页面 + 网络拦截首批评论 ────────────────
        tab.listen.start(COMMENT_API_PATTERN)
        opened = _open_post_page_with_retry(
            tab,
            page_url=page_url,
            task_id=task_id,
            phase_callback=_update_phase,
        )
        if not opened:
            logger.warning(f"评论抓取：帖子页面连续命中 HTTP 418，mid={mid}")
            return WeiboCommentFetchResult(truncated_reason="http_418_cooldown_exhausted")

        # 检查重定向
        current_url = tab.url or ""
        if "passport.weibo.com" in current_url or "security.weibo.com" in current_url:
            logger.warning(f"评论抓取：被重定向到登录/安全页面 URL={current_url}，放弃")
            return WeiboCommentFetchResult(truncated_reason="redirected_to_login")

        # 等待首个评论数据包
        first_data = None
        packet = _wait_comment_packet(tab, timeout=_FIRST_PACKET_TIMEOUT)
        if packet:
            first_data = _parse_packet_body(packet)

        # 首次没拦截到 → 滚动触发
        if not first_data:
            logger.info(f"评论 mid={mid} 首次拦截未获取数据，尝试滚动触发...")
            _scroll_for_comments(tab, task_id=task_id)
            packet = _wait_comment_packet(tab, timeout=_PACKET_TIMEOUT)
            if packet:
                first_data = _parse_packet_body(packet)

        # 停止网络拦截（后续用 Python requests）
        try:
            tab.listen.stop()
        except Exception:
            pass

        if not first_data or first_data.get("ok") != 1:
            logger.warning(f"评论 mid={mid} 首页数据获取失败")
            return WeiboCommentFetchResult(truncated_reason="first_page_failed")

        # 解析首页评论
        page_data = first_data.get("data", [])
        next_max_id = first_data.get("max_id", 0)
        total_number = first_data.get("total_number", 0)
        pages_fetched = 1

        # 保留原始数据供后续子评论补全
        for c in page_data:
            cid = str(c.get("id", ""))
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                all_raw_data.append(c)

        logger.info(
            f"评论 mid={mid} 首页拦截成功：{len(page_data)} 条顶层评论，"
            f"max_id={next_max_id}, "
            f"API total_number={total_number}（含所有层级子评论）"
        )
        if _update_phase:
            _update_phase(
                f"评论首页获取 {len(all_raw_data)} 条顶层（共 {total_number} 条含子评论）"
            )

        if not next_max_id:
            logger.info(f"评论 mid={mid} 首页即为全部（max_id=0）")

        # ─── 阶段 2：提取 Cookie → Python requests 翻页 ─────────────
        cookies_dict = _extract_cookies_dict(tab)
        xsrf_token = _get_xsrf_token(cookies_dict)
        if not xsrf_token:
            logger.warning(f"评论 mid={mid} 无法获取 XSRF-TOKEN，尝试继续...")

        actual_page_url = tab.url or page_url
        api_headers = _build_api_headers(xsrf_token, referer=actual_page_url)

        session = http_requests.Session()
        for name, value in cookies_dict.items():
            session.cookies.set(name, value, domain=".weibo.com")

        # 关闭标签页（后续不再需要浏览器）
        try:
            tab.close()
        except Exception:
            pass
        tab = None

        # ─── 翻页循环（仅在首页有 max_id 时才进入）──────────────────
        if next_max_id:
            page_num = 1
            max_pages = 50

            for _ in range(max_pages):
                if task_id:
                    check_signal(task_id)

                page_num += 1
                jittered_sleep(page_interval, task_id=task_id)

                api_url = _build_comment_api_url(
                    mid, max_id=next_max_id, uid=author_uid
                )

                data = _requests_fetch_page(session, api_url, api_headers)

                if not data:
                    logger.warning(f"评论 mid={mid} 第 {page_num} 页请求失败")
                    empty_page_count += 1
                    if empty_page_count >= _MAX_EMPTY_PAGES:
                        break
                    continue

                if data.get("ok") != 1:
                    logger.warning(
                        f"评论 API 返回异常 mid={mid} 第 {page_num} 页: ok={data.get('ok')}"
                    )
                    empty_page_count += 1
                    if empty_page_count >= _MAX_EMPTY_PAGES:
                        break
                    continue

                page_data = data.get("data", [])
                next_max_id = data.get("max_id", 0)
                total_number = data.get("total_number", total_number)
                pages_fetched = max(pages_fetched, page_num)

                new_top = 0
                for c in page_data:
                    cid = str(c.get("id", ""))
                    if cid and cid in seen_ids:
                        continue
                    if cid:
                        seen_ids.add(cid)
                    all_raw_data.append(c)
                    new_top += 1

                if new_top == 0:
                    empty_page_count += 1
                else:
                    empty_page_count = 0

                logger.info(
                    f"评论 mid={mid} 第 {page_num} 页：新增 {new_top} 条顶层，"
                    f"累计 {len(all_raw_data)} 条顶层，max_id={next_max_id}"
                )
                if _update_phase:
                    _update_phase(
                        f"评论翻页第 {page_num} 页，累计 {len(all_raw_data)} 条顶层评论"
                    )

                if len(all_raw_data) >= max_comments:
                    logger.info(f"评论 mid={mid} 顶层已达上限 {max_comments}，停止")
                    truncated_reason = f"top_level_limit_reached:{max_comments}"
                    break

                if not next_max_id:
                    logger.info(f"评论 mid={mid} 无更多分页（max_id=0），停止")
                    break

                if empty_page_count >= _MAX_EMPTY_PAGES:
                    logger.info(
                        f"评论 mid={mid} 连续 {_MAX_EMPTY_PAGES} 页无新数据，停止"
                    )
                    break

        # ─── 阶段 3：子评论补全 ──────────────────────────────────────
        if all_raw_data and session:
            from .sub_comment_fetcher import enrich_comments_with_subs

            new_subs = enrich_comments_with_subs(
                all_raw_data,
                session,
                api_headers,
                page_interval=max(page_interval * 0.5, 1.5),
                task_id=task_id,
                phase_callback=_update_phase,
            )
            if new_subs > 0:
                logger.info(
                    f"评论 mid={mid} 子评论补全完成，新增 {new_subs} 条"
                )
                if _update_phase:
                    _update_phase(f"二级评论补全完成，新增 {new_subs} 条")
                sub_comment_completion_status = "complete"
            elif all_raw_data:
                sub_comment_completion_status = "complete"

        # ─── 解析所有评论 ────────────────────────────────────────────
        for c in all_raw_data:
            comments.append(_parse_comment(c))

    except Exception as e:
        logger.error(f"评论抓取异常 mid={mid}: {e}", exc_info=True)
        if truncated_reason is None:
            truncated_reason = f"exception:{type(e).__name__}"
    finally:
        if tab is not None:
            try:
                tab.listen.stop()
            except Exception:
                pass
            try:
                tab.close()
            except Exception:
                pass

    tree_stats = collect_comment_tree_stats(comments)
    if sub_comment_completion_status == "top_level_only" and tree_stats.total_count > tree_stats.top_level_count:
        sub_comment_completion_status = "partial"
    if truncated_reason and sub_comment_completion_status == "complete":
        sub_comment_completion_status = "partial"
    comment_stats = build_comment_stats(
        post_comment_count=post_comment_count,
        api_claimed_total=total_number,
        fetched_total_count=tree_stats.total_count,
        fetched_top_level_count=tree_stats.top_level_count,
        max_depth=tree_stats.max_depth,
        sub_comment_completion_status=sub_comment_completion_status,
        truncated_reason=truncated_reason,
        pages_fetched=pages_fetched,
    )
    logger.info(
        f"评论抓取完成 mid={mid}，顶层 {tree_stats.top_level_count} 条，"
        f"含子评论共 {tree_stats.total_count} 条（API total_number={total_number}，"
        f"状态={sub_comment_completion_status}）"
    )
    return WeiboCommentFetchResult(
        comments=comments,
        fetched_total_count=comment_stats["fetched_total_count"],
        fetched_top_level_count=comment_stats["fetched_top_level_count"],
        api_claimed_total=comment_stats["api_claimed_total"],
        sub_comment_completion_status=sub_comment_completion_status,
        truncated_reason=truncated_reason,
        pages_fetched=pages_fetched,
    )


# ────────────────────────────────────────────────────────────
#  评论解析
# ────────────────────────────────────────────────────────────

def _parse_comment(c: dict) -> WeiboComment:
    """从 API 响应中解析一条评论。"""
    user = c.get("user", {})

    text = c.get("text_raw", "") or _clean_html(c.get("text", ""))

    sub_comments = []
    sub_comments_raw = c.get("comments", [])
    sub_comments_count = c.get("total_number", 0) or len(sub_comments_raw)
    for sc in sub_comments_raw:
        sub_comments.append(_parse_comment(sc))

    reply_to_user = ""
    reply_comment = c.get("reply_comment")
    if reply_comment:
        reply_user = reply_comment.get("user", {})
        reply_to_user = reply_user.get("screen_name", "")

    return WeiboComment(
        id=str(c.get("id", "")),
        text=text,
        author_name=user.get("screen_name", ""),
        author_id=str(user.get("id", "")),
        created_at=c.get("created_at", ""),
        likes=c.get("like_count", 0) or c.get("like_counts", 0) or 0,
        source=c.get("source", ""),
        avatar_url=user.get("avatar_hd", "") or user.get("profile_image_url", ""),
        is_author=bool(c.get("is_mblog_author", False)),
        verified=bool(user.get("verified", False)),
        verified_reason=user.get("verified_reason", ""),
        gender=user.get("gender", ""),
        location=user.get("location", ""),
        followers_count=user.get("followers_count", 0),
        reply_to_user=reply_to_user,
        sub_comments=sub_comments,
        sub_comments_count=sub_comments_count,
    )


def _clean_html(text: str) -> str:
    """清理评论中的 HTML 标签。"""
    text = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*/?\s*>', r"\1", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<a[^>]*>([^<]*)</a>", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
