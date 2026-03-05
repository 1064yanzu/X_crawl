"""
微博搜索主入口。
参考 x_searcher.py 的结构，支持断点恢复和检查点保存。

修复：
1. 正确的 Cookie 注入时序（先到域名再注入）
2. Tab 崩溃恢复机制（Target crashed / 超时后重建 tab 并重试）
3. 反爬检测（验证码页面、登录跳转检测）
4. 搜索页等待优化（替代固定 sleep）
"""
from __future__ import annotations

import json
import logging
import time
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

CHECKPOINTS_DIR = Path(__file__).parent.parent.parent / "checkpoints"

# 重试配置
MAX_PAGE_RETRIES = 2
RETRY_DELAY = 5


@dataclass
class WeiboSearchResult:
    """微博搜索结果"""

    posts: list = field(default_factory=list)
    resumed: bool = False


def _load_checkpoint(task_id: str) -> dict:
    """加载断点。"""
    path = CHECKPOINTS_DIR / f"weibo_{task_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_checkpoint(task_id: str, state: dict) -> None:
    """保存断点。"""
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKPOINTS_DIR / f"weibo_{task_id}.json"
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _check_anti_crawl(tab) -> Optional[str]:
    """
    检测页面是否触发了反爬拦截。

    Returns:
        None — 正常页面
        str  — 反爬原因描述
    """
    try:
        url = tab.url or ""
        # 1. 跳转到了登录页
        if "passport.weibo.com" in url:
            return "被重定向到登录页（Cookie 可能过期）"
        if "security.weibo.com" in url:
            return "触发安全验证页面"

        # 2. 检查页面内容（使用 DrissionPage 的元素查找）
        # 验证码相关元素
        try:
            html_text = tab.html
            if html_text and len(html_text) < 2000:
                # 页面内容过短，可能是空白或错误页
                if "验证" in html_text or "verify" in html_text.lower():
                    return "页面包含验证码提示"
                if "请登录" in html_text:
                    return "页面要求登录"
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"反爬检测异常（忽略）: {e}")

    return None


def _get_fresh_tab():
    """获取一个新的 tab（用于崩溃后恢复）。先重置浏览器再创建新 tab。"""
    from crawler.browser import get_new_tab, reset_browser
    try:
        reset_browser()
    except Exception:
        pass
    return get_new_tab()


def _get_tab_with_retry(max_retries: int = 2):
    """
    带重试的 tab 获取。浏览器卡死时自动重置并重建。
    """
    from crawler.browser import get_new_tab, reset_browser
    for attempt in range(max_retries + 1):
        try:
            tab = get_new_tab()
            return tab
        except Exception as e:
            logger.warning(
                f"获取浏览器 Tab 失败 (attempt {attempt + 1}/{max_retries + 1}): {e}"
            )
            if attempt < max_retries:
                logger.info("正在重置浏览器并重试...")
                try:
                    reset_browser()
                except Exception:
                    pass
                time.sleep(3)
            else:
                raise


def _safe_get_html(tab, url: str, wait_seconds: float = 3.0) -> tuple[Optional[str], Optional[str]]:
    """
    安全获取页面 HTML。

    Returns:
        (html, error) — 成功时 error 为 None，失败时 html 为 None
    """
    try:
        tab.get(url)
        time.sleep(wait_seconds)

        # 检查是否被重定向到非搜索页面
        current_url = tab.url or ""
        if "s.weibo.com" in url and current_url:
            # 如果目标是搜索页面但被重定向到了其他页面
            if "s.weibo.com" not in current_url:
                return None, f"被重定向到非搜索页: {current_url}"

        # 检查反爬
        anti_crawl_reason = _check_anti_crawl(tab)
        if anti_crawl_reason:
            return None, f"反爬拦截: {anti_crawl_reason}"

        html = tab.html
        if not html:
            return None, "页面 HTML 为空"
        return html, None
    except Exception as e:
        error_str = str(e)
        return None, error_str


def search(
    keyword: str,
    max_count: int = 100,
    task_id: Optional[str] = None,
    resume: bool = True,
    fetch_comments: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    _parent_accumulated: Optional[list] = None,
) -> WeiboSearchResult:
    """
    微博关键词搜索主入口。
    返回 WeiboSearchResult，其中 posts 是 WeiboPost.to_dict() 的列表。
    """
    from config import settings
    from api.services.task_manager import update_preview_tweets, update_task_phase
    from crawler.utils import check_signal, StopSignal, jittered_sleep, interruptible_sleep
    from .auth import ensure_weibo_login, ensure_search_cookies
    from .html_parser import parse_search_page
    from .comment_fetcher import fetch_comments as do_fetch_comments

    tab = _get_tab_with_retry()

    # ── 1. 登录验证 ──────────────────────────────────────────
    if task_id:
        update_task_phase(task_id, "正在验证微博登录状态...")
    try:
        logged_in = ensure_weibo_login(tab)
        if not logged_in:
            logger.warning("微博未登录，将以游客模式尝试（可能受限）")
    except Exception as e:
        logger.warning(f"微博登录验证失败: {e}")

    # ── 2. 搜索 Cookie 准备 ──────────────────────────────────
    if task_id:
        update_task_phase(task_id, "正在准备搜索 Cookie...")
    try:
        ensure_search_cookies(tab)
    except Exception as e:
        logger.warning(f"搜索 Cookie 准备失败: {e}")

    # ── 3. 断点恢复 ──────────────────────────────────────────
    checkpoint: dict = {}
    if resume and task_id:
        checkpoint = _load_checkpoint(task_id)

    start_page: int = checkpoint.get("page", 1)
    all_posts_dicts: list[dict] = checkpoint.get("posts", [])
    resumed = bool(checkpoint)

    max_pages: int = settings.weibo_max_pages
    page_interval: float = settings.weibo_search_page_interval

    # ── 日期范围分割（突破 50 页限制）────────────────────────
    # 注意：如果 _parent_accumulated 不为 None，说明当前调用已经是父级分段的子段，
    # 不应再次分割，否则会导致 43 个月 × 10 个子段 = 430 个切片的指数级膨胀
    if start_date and end_date and not resumed and _parent_accumulated is None:
        from .date_splitter import split_date_range
        date_ranges = split_date_range(
            start_date, 
            end_date, 
            max_pages=max_pages,
            target_count=max_count,
        )
        if len(date_ranges) > 1:
            logger.info(
                f"日期范围已分割为 {len(date_ranges)} 个子范围，将依次搜索"
            )
            if task_id:
                update_task_phase(
                    task_id,
                    f"日期范围已拆分为 {len(date_ranges)} 段，开始分段搜索..."
                )
            all_results: list[dict] = []
            try:
                for seg_idx, (seg_start, seg_end) in enumerate(date_ranges):
                    check_signal(task_id)  # 支持 pause/stop
                    if task_id:
                        update_task_phase(
                            task_id,
                            f"正在搜索第 {seg_idx + 1}/{len(date_ranges)} 段: "
                            f"{seg_start} ~ {seg_end}"
                        )
                    # 递归调用自身，每段单独搜索
                    remaining = max(0, max_count - len(all_results)) if max_count > 0 else 0
                    if max_count > 0 and remaining <= 0:
                        break
                    seg_result = search(
                        keyword=keyword,
                        max_count=remaining if max_count > 0 else 0,
                        task_id=task_id,
                        resume=False,
                        fetch_comments=fetch_comments,
                        start_date=seg_start,
                        end_date=seg_end,
                        _parent_accumulated=all_results,
                    )
                    all_results.extend(seg_result.posts)
                    # 实时推送合并后的预览
                    if task_id:
                        update_preview_tweets(
                            task_id,
                            current_page=seg_idx + 1,
                            tweets_for_preview=all_results,
                        )
            except StopSignal:
                logger.info(f"收到停止信号，微博分段搜索终止 task_id={task_id}")
            return WeiboSearchResult(posts=all_results, resumed=False)

    # 构建搜索 URL
    kw_encoded = quote(keyword)

    consecutive_errors = 0  # 连续错误计数

    try:
        for page in range(start_page, max_pages + 1):
            # 检查暂停/停止信号
            check_signal(task_id)

            # 构建 URL
            url = f"https://s.weibo.com/weibo?q={kw_encoded}&typeall=1&suball=1&count=50&page={page}"
            if start_date and end_date:
                url += f"&timescope=custom:{start_date}:{end_date}"

            logger.info(f"微博搜索第 {page} 页: {url}")
            if task_id:
                update_task_phase(task_id, f"正在获取微博搜索第 {page} 页...")

            # ── 带重试的页面获取 ──────────────
            html = None
            page_error = None

            for retry in range(MAX_PAGE_RETRIES + 1):
                html, page_error = _safe_get_html(tab, url)
                if html:
                    break

                # 错误处理
                is_crash = page_error and ("crashed" in page_error.lower() or "timeout" in page_error.lower())
                logger.warning(
                    f"获取微博搜索页失败 page={page} retry={retry}/{MAX_PAGE_RETRIES}: {page_error}"
                )

                if is_crash and retry < MAX_PAGE_RETRIES:
                    # Tab 崩溃：重建 tab
                    logger.info("检测到 Tab 崩溃/超时，正在重建...")
                    try:
                        tab = _get_fresh_tab()
                        # 重新注入 Cookie
                        from .cookie_manager import load_cookies, inject_cookies_to_tab
                        cookies = load_cookies()
                        if cookies:
                            tab.get("https://s.weibo.com")
                            time.sleep(1)
                            inject_cookies_to_tab(tab, cookies)
                            time.sleep(1)
                    except Exception as e:
                        logger.error(f"重建 Tab 失败: {e}")
                    interruptible_sleep(RETRY_DELAY, task_id=task_id)
                elif "反爬拦截" in (page_error or ""):
                    # 反爬拦截：加大延迟后重试
                    wait = RETRY_DELAY * (retry + 1) * 2
                    logger.warning(f"触发反爬，等待 {wait}s 后重试...")
                    time.sleep(wait)
                else:
                    interruptible_sleep(RETRY_DELAY, task_id=task_id)

            if not html:
                consecutive_errors += 1
                logger.error(f"获取微博搜索页最终失败 page={page}: {page_error}")
                if consecutive_errors >= 3:
                    logger.error("连续 3 页获取失败，终止搜索")
                    break
                continue
            else:
                consecutive_errors = 0

            # ── 解析结果 ─────────────────────
            try:
                posts, has_next, total_pages = parse_search_page(html)
            except Exception as e:
                logger.error(f"解析微博搜索结果失败 page={page}: {e}")
                break

            if page == start_page and total_pages > 0:
                logger.info(f"微博搜索共 {total_pages} 页")
                if task_id:
                    update_task_phase(
                        task_id,
                        f"微博搜索共 {total_pages} 页，正在获取第 {page} 页..."
                    )

            if not posts:
                logger.info(f"微博搜索第 {page} 页无结果，终止")
                break

            need_comments = fetch_comments and any(
                p.comments_count > 0 for p in posts
            )
            for post_idx, post in enumerate(posts):
                # 按需抓取评论
                if fetch_comments and post.comments_count > 0:
                    if task_id:
                        update_task_phase(
                            task_id,
                            f"正在抓取第 {page} 页第 {post_idx + 1}/{len(posts)} 条微博的评论..."
                        )
                    try:
                        comments = do_fetch_comments(
                            tab,
                            post.mid,
                            author_uid=post.author_id,
                            max_comments=settings.weibo_max_comments_per_post,
                            page_interval=settings.weibo_comment_page_interval,
                            task_id=task_id,
                        )
                        post.comments = comments
                    except StopSignal:
                        raise  # 停止信号向上传播
                    except Exception as e:
                        logger.warning(f"抓取评论失败 mid={post.mid}: {e}")
                all_posts_dicts.append(post.to_dict())

            # 评论抓取后导航回搜索域名，避免后续页面抓取失败
            if need_comments:
                try:
                    tab.get("https://s.weibo.com")
                    interruptible_sleep(1.0, task_id=task_id)
                except Exception:
                    pass

            logger.info(
                f"微博搜索第 {page} 页完成，"
                f"本页 {len(posts)} 条，累计 {len(all_posts_dicts)} 条"
            )

            # 实时上报进度给前端（合并父级已累积数据，确保前端看到的是全任务数据）
            combined = (_parent_accumulated or []) + all_posts_dicts
            if task_id:
                update_task_phase(
                    task_id,
                    f"微博搜索第 {page} 页完成，累计 {len(combined)} 条"
                )
                update_preview_tweets(
                    task_id,
                    current_page=page,
                    tweets_for_preview=combined,
                )

            # 保存检查点
            if task_id:
                _save_checkpoint(
                    task_id,
                    {
                        "page": page + 1,
                        "posts": all_posts_dicts,
                        "keyword": keyword,
                    },
                )

            # 检查是否达到 max_count
            if max_count > 0 and len(all_posts_dicts) >= max_count:
                break

            if not has_next:
                break

            jittered_sleep(page_interval, task_id=task_id)

    except StopSignal:
        logger.info(f"收到停止信号，微博搜索终止 task_id={task_id}")

    return WeiboSearchResult(posts=all_posts_dicts, resumed=resumed)

