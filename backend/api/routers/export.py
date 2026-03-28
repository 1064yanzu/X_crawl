"""
数据导出路由
GET /api/v1/export/{task_id}?format=csv   - 导出为 CSV（UTF-8 BOM）
GET /api/v1/export/{task_id}?format=excel - 导出为 Excel（xlsx）
"""
import io
import csv
import re
import logging
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.services import task_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/export", tags=["数据导出"])

# 导出字段定义（顺序即为列顺序）
EXPORT_FIELDS = [
    # 基础
    ("platform", "平台"),
    ("id", "推文ID"),
    ("conversation_id", "对话ID"),
    ("created_at", "发布时间"),
    ("source", "发推客户端"),
    # 作者
    ("author_name", "作者昵称"),
    ("author_username", "作者账号"),
    ("author_id", "作者ID"),
    ("author_verified", "认证状态"),
    ("author_followers", "作者粉丝数"),
    ("is_author", "是否楼主"),
    # 内容
    ("text", "推文内容"),
    ("lang", "语言"),
    # 互动指标
    ("like_count", "点赞数"),
    ("retweet_count", "转发数"),
    ("reply_count", "回复数"),
    ("quote_count", "引用数"),
    ("view_count", "浏览数"),
    ("bookmark_count", "收藏数"),
    # 链接
    ("url", "推文链接"),
    # 数据类型（区分原帖/回复）
    ("row_type", "数据类型"),
    ("parent_tweet_id", "所属推文ID"),
    # 回复关系
    ("reply_to_tweet_id", "回复目标推文ID"),
    ("reply_to_username", "回复目标用户"),
    # 类型标记
    ("is_retweet", "是否转推"),
    ("is_quote", "是否引用"),
    ("is_reply", "是否回复"),
    # 实体
    ("hashtags", "话题标签"),
    ("user_mentions_text", "提及用户"),
    # 媒体
    ("has_media", "含媒体"),
    ("media_types", "媒体类型"),
    ("media_urls", "媒体链接"),
]


def _flatten_tweet(tweet: dict) -> dict:
    """将嵌套推文字典展平为导出所需的扁平结构"""
    author = tweet.get("author") or {}
    if not isinstance(author, dict):
        author = {}
    metrics = tweet.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    reply_to = tweet.get("reply_to") or {}
    if not isinstance(reply_to, dict):
        reply_to = {}
    media_list = tweet.get("media") or []

    flat = {}
    for field, _ in EXPORT_FIELDS:
        value = tweet.get(field)
        if value is not None:
            flat[field] = value
            continue

        # 从嵌套结构提取
        if field == "author_name":
            value = author.get("name", "")
        elif field == "author_username":
            value = author.get("username", "") or author.get("screen_name", "")
        elif field == "author_id":
            value = author.get("id", "")
        elif field == "author_verified":
            verified = author.get("verified", False)
            blue = author.get("is_blue_verified", False)
            value = "蓝标认证" if blue else ("已认证" if verified else "")
        elif field == "author_followers":
            value = author.get("followers_count", "")
        elif field == "is_author":
            # 微博评论数据中 is_author 标识是否为原帖作者
            is_author_val = tweet.get("is_author", False)
            value = "是" if is_author_val else ""
        elif field == "like_count":
            value = tweet.get("like_count") or metrics.get("likes", "")
        elif field == "retweet_count":
            value = tweet.get("retweet_count") or metrics.get("retweets", "")
        elif field == "reply_count":
            value = tweet.get("reply_count") or metrics.get("replies", "")
        elif field == "quote_count":
            value = tweet.get("quote_count") or metrics.get("quotes", "")
        elif field == "view_count":
            value = tweet.get("view_count") or metrics.get("views", "")
        elif field == "bookmark_count":
            value = tweet.get("bookmark_count") or metrics.get("bookmarks", "")
        elif field == "reply_to_tweet_id":
            value = reply_to.get("tweet_id", "")
        elif field == "reply_to_username":
            value = reply_to.get("screen_name", "")
        elif field == "is_reply":
            value = bool(reply_to.get("tweet_id"))
        elif field == "has_media":
            value = bool(media_list or tweet.get("photos") or tweet.get("videos"))
        elif field == "hashtags":
            tags = tweet.get("hashtags", [])
            value = ", ".join(tags) if isinstance(tags, list) else str(tags) if tags else ""
        elif field == "user_mentions_text":
            mentions = tweet.get("user_mentions", [])
            if isinstance(mentions, list):
                names = [m.get("screen_name", "") for m in mentions if isinstance(m, dict)]
                value = ", ".join(n for n in names if n)
            else:
                value = ""
        elif field == "media_types":
            if isinstance(media_list, list):
                types = [m.get("type", "") for m in media_list if isinstance(m, dict)]
                value = ", ".join(t for t in types if t)
            else:
                value = ""
        elif field == "media_urls":
            if isinstance(media_list, list):
                urls = []
                for m in media_list:
                    if not isinstance(m, dict):
                        continue
                    u = m.get("video_url") or m.get("url", "")
                    if u:
                        urls.append(u)
                value = ", ".join(urls)
            else:
                value = ""
        else:
            value = ""
        flat[field] = value
    return flat


def _as_dict(value: object) -> dict:
    """将可能为 None/非 dict 的字段安全归一化为 dict。"""
    return value if isinstance(value, dict) else {}


def _collect_replies(
    replies: list[dict],
    parent_id: str,
    platform: str,
    parent_author_name: str = "",
) -> list[dict]:
    """递归收集回复/评论，标注数据类型、所属推文ID、回复目标用户。

    对于一级评论（直接回复原帖的），如果本身没有 reply_to 字段，
    则自动填充 reply_to 为原帖作者。
    """
    all_replies = []
    for reply in replies:
        reply_copy = dict(reply)
        reply_copy["row_type"] = "评论"
        reply_copy["parent_tweet_id"] = parent_id
        reply_copy.setdefault("platform", platform)

        # 如果评论自身没有 reply_to 信息（一级评论）,
        # 自动填充为原帖/父级作者
        existing_reply_to = _as_dict(reply_copy.get("reply_to"))
        if not existing_reply_to.get("screen_name") and parent_author_name:
            normalized_reply_to = dict(existing_reply_to)
            normalized_reply_to["screen_name"] = parent_author_name
            reply_copy["reply_to"] = normalized_reply_to

        all_replies.append(reply_copy)

        nested = reply.get("replies", [])
        if nested and isinstance(nested, list):
            # 子评论的 parent_author_name 用当前评论的作者
            current_author = ""
            author = reply.get("author") or {}
            if isinstance(author, dict):
                current_author = author.get("name", "") or author.get("screen_name", "")
            all_replies.extend(_collect_replies(
                nested,
                parent_id=parent_id,
                platform=platform,
                parent_author_name=current_author or parent_author_name,
            ))
    return all_replies


def _collect_all_rows(tweets: list[dict], platform: str) -> list[dict]:
    """递归收集所有推文及其嵌套评论/回复，展平为独立行，并标注数据类型"""
    all_rows = []
    for tweet in tweets:
        tweet_copy = dict(tweet)
        tweet_copy["row_type"] = "原帖"
        tweet_copy["parent_tweet_id"] = ""
        tweet_copy.setdefault("platform", platform)
        all_rows.append(tweet_copy)

        # 提取原帖作者名称，供一级评论自动填充 reply_to
        author = tweet.get("author") or {}
        parent_author_name = ""
        if isinstance(author, dict):
            parent_author_name = (
                author.get("name", "")
                or author.get("screen_name", "")
            )

        replies = tweet.get("replies", [])
        if replies and isinstance(replies, list):
            all_rows.extend(_collect_replies(
                replies,
                parent_id=tweet.get("id", ""),
                platform=platform,
                parent_author_name=parent_author_name,
            ))
    return all_rows


def _make_row_dedup_key(row: dict) -> tuple[str, str, str, str, str]:
    """生成导出去重键：平台 + ID + 文本 + 数据类型 + 所属推文 ID。"""
    return (
        str(row.get("platform", "")),
        str(row.get("id", "")),
        str(row.get("text", "")),
        str(row.get("row_type", "")),
        str(row.get("parent_tweet_id", "")),
    )


def _dedup_rows(rows: list[dict]) -> list[dict]:
    """根据核心字段去重，完全相同的帖子/评论只保留第一条。"""
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[dict] = []
    for row in rows:
        key = _make_row_dedup_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _get_task_data(task_id: str, *, deduplicate: bool = False) -> tuple[dict, list[dict]]:
    """获取任务元信息和推文列表（含回复展平），不存在则抛 404"""
    task = task_manager.get_task_export_payload(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    tweets = task.get("tweets", [])
    if not tweets:
        raise HTTPException(status_code=204, detail="该任务暂无数据可供导出")

    # 递归展平：将每条推文的 replies（及嵌套 replies）加入导出列表
    all_rows = _collect_all_rows(tweets, task.get("platform", "x"))

    tweet_count = len(tweets)
    reply_count = len(all_rows) - tweet_count
    logger.info(
        f"导出任务 {task_id}: {tweet_count} 条推文 + {reply_count} 条回复 = {len(all_rows)} 行"
    )
    if reply_count == 0 and task.get("fetch_replies"):
        logger.warning(
            f"任务 {task_id} 开启了回复抓取但导出回复数为 0，"
            f"请检查推文数据中 replies 字段是否存在"
        )

    if deduplicate:
        before = len(all_rows)
        all_rows = _dedup_rows(all_rows)
        removed = before - len(all_rows)
        if removed > 0:
            logger.info(f"导出去重: 移除 {removed} 条重复数据，剩余 {len(all_rows)} 行")

    return task, all_rows


def _make_filename(task: dict, ext: str) -> str:
    """根据关键词+时间生成导出文件名"""
    keyword = task.get("keyword", "export")
    # 清理关键词中不适合做文件名的字符
    clean_keyword = re.sub(r'[\\/:*?"<>|\s]+', '_', keyword).strip('_')
    # 截断过长的关键词
    if len(clean_keyword) > 50:
        clean_keyword = clean_keyword[:50]
    # 生成时间戳
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{clean_keyword}_{now}.{ext}"


# ─── CSV 导出 ──────────────────────────────────────────────────────────────

def _build_csv(tweets: list[dict]) -> bytes:
    buf = io.StringIO()
    headers = [label for _, label in EXPORT_FIELDS]
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for tweet in tweets:
        flat = _flatten_tweet(tweet)
        writer.writerow({label: flat[field] for field, label in EXPORT_FIELDS})
    # UTF-8 BOM，兼容 Windows Excel 直接打开
    return "\ufeff".encode("utf-8") + buf.getvalue().encode("utf-8")


@router.get("/{task_id}/csv", summary="导出推文为 CSV")
async def export_csv(
    task_id: str,
    deduplicate: bool = Query(default=False, description="是否对导出数据去重（完全相同的帖子/评论只保留一条）"),
):
    task, tweets = _get_task_data(task_id, deduplicate=deduplicate)
    data = _build_csv(tweets)
    filename = _make_filename(task, "csv")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ─── Excel 导出 ────────────────────────────────────────────────────────────

def _build_excel(tweets: list[dict]) -> bytes:
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="缺少 openpyxl 依赖，请在后端执行: pip install openpyxl"
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "推文数据"

    # 表头样式
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(fill_type="solid", fgColor="1D9BF0")  # X 品牌蓝
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=False)

    # 写表头
    headers = [label for _, label in EXPORT_FIELDS]
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    # 写数据
    for row_idx, tweet in enumerate(tweets, 2):
        flat = _flatten_tweet(tweet)
        for col_idx, (field, _) in enumerate(EXPORT_FIELDS, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=flat.get(field, ""))
            cell.alignment = Alignment(wrap_text=False, vertical="top")

    # 自动列宽（与 EXPORT_FIELDS 一一对应）
    col_widths = [
        10,  # 平台
        20,  # 推文ID
        20,  # 对话ID
        20,  # 发布时间
        18,  # 发推客户端
        16,  # 作者昵称
        16,  # 作者账号
        18,  # 作者ID
        10,  # 认证状态
        12,  # 作者粉丝数
        10,  # 是否楼主
        60,  # 推文内容
         8,  # 语言
        10,  # 点赞数
        10,  # 转发数
        10,  # 回复数
        10,  # 引用数
        10,  # 浏览数
        10,  # 收藏数
        50,  # 推文链接
        10,  # 数据类型
        20,  # 所属推文ID
        20,  # 回复目标推文ID
        16,  # 回复目标用户
        10,  # 是否转推
        10,  # 是否引用
        10,  # 是否回复
        20,  # 话题标签
        20,  # 提及用户
        10,  # 含媒体
        12,  # 媒体类型
        50,  # 媒体链接
    ]
    for i, width in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width

    # 冻结首行
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


@router.get("/{task_id}/excel", summary="导出推文为 Excel（xlsx）")
async def export_excel(
    task_id: str,
    deduplicate: bool = Query(default=False, description="是否对导出数据去重（完全相同的帖子/评论只保留一条）"),
):
    task, tweets = _get_task_data(task_id, deduplicate=deduplicate)
    data = _build_excel(tweets)
    filename = _make_filename(task, "xlsx")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ─── 通用接口（向后兼容）─────────────────────────────────────────────────────

@router.get("/{task_id}", summary="导出推文（format=csv|excel）")
async def export_any(
    task_id: str,
    format: Literal["csv", "excel"] = Query(default="csv", description="导出格式"),
    deduplicate: bool = Query(default=False, description="是否对导出数据去重"),
):
    if format == "excel":
        return await export_excel(task_id, deduplicate=deduplicate)
    return await export_csv(task_id, deduplicate=deduplicate)
