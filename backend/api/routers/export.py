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


def _collect_all_rows(tweets: list[dict]) -> list[dict]:
    """递归收集所有推文及其嵌套回复，展平为独立行"""
    all_rows = []
    for tweet in tweets:
        all_rows.append(tweet)
        replies = tweet.get("replies", [])
        if replies and isinstance(replies, list):
            # 递归展平嵌套回复
            all_rows.extend(_collect_all_rows(replies))
    return all_rows


def _get_task_data(task_id: str) -> tuple[dict, list[dict]]:
    """获取任务元信息和推文列表（含回复展平），不存在则抛 404"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    tweets = task.get("tweets", [])
    if not tweets:
        raise HTTPException(status_code=204, detail="该任务暂无数据可供导出")

    # 递归展平：将每条推文的 replies（及嵌套 replies）加入导出列表
    all_rows = _collect_all_rows(tweets)

    tweet_count = len(tweets)
    reply_count = len(all_rows) - tweet_count
    logger.info(
        f"导出任务 {task_id}: {tweet_count} 条推文 + {reply_count} 条回复 = {len(all_rows)} 行"
    )

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
async def export_csv(task_id: str):
    task, tweets = _get_task_data(task_id)
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
        20,  # 推文ID
        20,  # 对话ID
        20,  # 发布时间
        18,  # 发推客户端
        16,  # 作者昵称
        16,  # 作者账号
        18,  # 作者ID
        10,  # 认证状态
        12,  # 作者粉丝数
        60,  # 推文内容
         8,  # 语言
        10,  # 点赞数
        10,  # 转发数
        10,  # 回复数
        10,  # 引用数
        10,  # 浏览数
        10,  # 收藏数
        50,  # 推文链接
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
async def export_excel(task_id: str):
    task, tweets = _get_task_data(task_id)
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
):
    if format == "excel":
        return await export_excel(task_id)
    return await export_csv(task_id)
