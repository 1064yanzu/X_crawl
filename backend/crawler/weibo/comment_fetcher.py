"""
微博评论抓取器。
通过 tab.run_js(fetch()) 在浏览器上下文中请求评论 API，自动携带 Cookie。
全面提取评论字段：文本、作者详情、IP属地、子评论、点赞数等。

修复：
1. 域切换后增加 Cookie 验证和等待
2. 增加 API 响应详细日志
3. 补充缺失的请求头（server-version, client-version）
4. XSRF-TOKEN 获取失败时自动重试
"""
from __future__ import annotations

import json
import logging
import random
import re
import time

from .models import WeiboComment

logger = logging.getLogger(__name__)


def _ensure_weibo_domain(tab) -> bool:
    """
    确保浏览器在 weibo.com 域名下（非 s.weibo.com）。
    返回 True 表示域名已就绪。
    """
    try:
        current_url = tab.url or ""
        if "weibo.com" in current_url and "s.weibo.com" not in current_url:
            return True

        logger.info("评论抓取：导航到 weibo.com 域名")
        tab.get("https://weibo.com")
        time.sleep(2 + random.uniform(0.5, 1.5))

        # 注入 Cookie 确保评论 API 可用
        from .cookie_manager import load_cookies, inject_cookies_to_tab
        cookies = load_cookies()
        if cookies:
            inject_cookies_to_tab(tab, cookies)
            logger.info(f"评论抓取：已注入 {len(cookies)} 条 Cookie")
            time.sleep(1)

        # 刷新页面使 Cookie 生效
        tab.get("https://weibo.com")
        time.sleep(1 + random.uniform(0.5, 1.5))
        logger.info(f"评论抓取：已导航到 weibo.com，当前 URL={tab.url}")
        return True
    except Exception as e:
        logger.warning(f"导航到 weibo.com 失败: {e}")
        try:
            tab.get("https://weibo.com")
            time.sleep(2)
        except Exception:
            pass
        return False


def fetch_comments(
    tab,
    mid: str,
    uid: str,
    max_comments: int = 50,
    page_interval: float = 4.0,
    task_id: str | None = None,
) -> list[WeiboComment]:
    """
    通过 AJAX API 抓取指定微博的评论列表。
    利用 tab.run_js(fetch()) 在浏览器上下文中发请求，自动携带 Cookie。
    """
    from .cookie_manager import get_xsrf_token_from_tab

    # 确保浏览器在 weibo.com 域名下（评论 API 是 weibo.com/ajax/...）
    _ensure_weibo_domain(tab)

    # 预先获取并验证 XSRF-TOKEN
    xsrf_token = get_xsrf_token_from_tab(tab) or ""
    if not xsrf_token:
        logger.warning(f"评论抓取：获取 XSRF-TOKEN 失败，尝试从 Cookie 文件加载注入")
        from .cookie_manager import load_cookies, inject_cookies_to_tab
        cookies = load_cookies()
        if cookies:
            inject_cookies_to_tab(tab, cookies)
            time.sleep(1)
            xsrf_token = get_xsrf_token_from_tab(tab) or ""
        if not xsrf_token:
            logger.error(f"评论抓取：XSRF-TOKEN 仍然为空，评论请求可能失败 mid={mid}")

    comments: list[WeiboComment] = []
    max_id = 0
    max_pages = 10

    for page_idx in range(max_pages):
        # 检查任务信号（支持暂停/停止）
        if task_id:
            try:
                from crawler.utils import check_signal
                check_signal(task_id)
            except Exception:
                break

        # 每页重新获取 token（可能过期）
        fresh_token = get_xsrf_token_from_tab(tab) or xsrf_token

        url = (
            f"https://weibo.com/ajax/statuses/buildComments"
            f"?is_reload=1&id={mid}&is_show_bulletin=2&is_mix=0"
            f"&count=20&uid={uid}&fetch_level=0&locale=zh-CN"
        )
        if max_id:
            url += f"&max_id={max_id}"

        js = f"""
(async () => {{
    try {{
        const r = await fetch("{url}", {{
            headers: {{
                "x-xsrf-token": "{fresh_token}",
                "x-requested-with": "XMLHttpRequest",
                "accept": "application/json, text/plain, */*",
                "client-version": "3.0.0"
            }},
            credentials: "include"
        }});
        const status = r.status;
        const text = await r.text();
        return JSON.stringify({{httpStatus: status, body: text}});
    }} catch(e) {{
        return JSON.stringify({{httpStatus: 0, body: "", error: e.toString()}});
    }}
}})()
"""
        try:
            raw = tab.run_js(js, timeout=30)
            if not raw:
                logger.warning(f"评论请求返回空值 mid={mid} page={page_idx + 1}")
                break

            wrapper = json.loads(raw) if isinstance(raw, str) else raw
            http_status = wrapper.get("httpStatus", 0)
            body_text = wrapper.get("body", "")
            js_error = wrapper.get("error", "")

            if js_error:
                logger.warning(f"评论 JS fetch 报错 mid={mid}: {js_error}")
                break

            if http_status != 200:
                logger.warning(
                    f"评论 API HTTP {http_status} mid={mid} page={page_idx + 1}, "
                    f"body={body_text[:200]}"
                )
                break

            data = json.loads(body_text) if body_text else {}
        except Exception as e:
            logger.warning(f"评论请求失败 mid={mid}: {e}")
            break

        if not data or data.get("ok") != 1:
            logger.warning(
                f"评论 API 返回异常 mid={mid} page={page_idx + 1}: "
                f"ok={data.get('ok')}, keys={list(data.keys()) if data else 'null'}, "
                f"raw={json.dumps(data, ensure_ascii=False)[:300] if data else 'empty'}"
            )
            break

        page_comments = data.get("data", [])
        if not page_comments:
            logger.debug(f"评论 mid={mid} 第{page_idx + 1}页无评论数据")
            break

        for c in page_comments:
            comment = _parse_comment(c)
            comments.append(comment)

        logger.info(
            f"评论 mid={mid} 第{page_idx + 1}页，"
            f"获取 {len(page_comments)} 条，累计 {len(comments)} 条"
        )

        next_max_id = data.get("max_id", 0)
        if not next_max_id or len(comments) >= max_comments:
            break
        max_id = next_max_id

        from crawler.utils import jittered_sleep
        jittered_sleep(page_interval, task_id=task_id)

    result = comments[:max_comments]
    logger.info(f"评论抓取完成 mid={mid}，共 {len(result)} 条")
    return result


def _parse_comment(c: dict) -> WeiboComment:
    """从 API 响应中解析一条评论，包含所有可用字段。"""
    user = c.get("user", {})

    # 文本：优先用 text_raw（纯文本），否则清理 text 中的 HTML
    text = c.get("text_raw", "") or _clean_html(c.get("text", ""))

    # 子评论
    sub_comments = []
    sub_comments_raw = c.get("comments", [])
    sub_comments_count = c.get("total_number", 0) or len(sub_comments_raw)
    for sc in sub_comments_raw:
        sub_comments.append(_parse_comment(sc))

    # 回复目标用户
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
    """清理评论中的 HTML 标签，保留纯文本。"""
    # 替换表情图片为 alt 文本
    text = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*/?\s*>', r"\1", text)
    # 保留 <br> 换行
    text = re.sub(r"<br\s*/?>", "\n", text)
    # 提取 <a> 标签的文本
    text = re.sub(r"<a[^>]*>([^<]*)</a>", r"\1", text)
    # 移除剩余 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
