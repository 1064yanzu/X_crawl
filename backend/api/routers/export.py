"""
数据导出路由
GET /api/v1/export/{task_id}?format=csv   - 导出为 CSV（UTF-8 BOM）
GET /api/v1/export/{task_id}?format=excel - 导出为 Excel（xlsx）
"""
import io
import csv
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.services import task_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/export", tags=["数据导出"])

# 导出字段定义（顺序即为列顺序）
EXPORT_FIELDS = [
    ("id", "推文ID"),
    ("created_at", "发布时间"),
    ("author_name", "作者昵称"),
    ("author_username", "作者账号"),
    ("text", "推文内容"),
    ("like_count", "点赞数"),
    ("retweet_count", "转发数"),
    ("reply_count", "回复数"),
    ("quote_count", "引用数"),
    ("view_count", "浏览数"),
    ("url", "推文链接"),
    ("lang", "语言"),
    ("is_retweet", "是否转推"),
    ("has_media", "含媒体"),
]


def _flatten_tweet(tweet: dict) -> dict:
    """将嵌套推文字典展平为导出所需的扁平结构"""
    flat = {}
    for field, _ in EXPORT_FIELDS:
        value = tweet.get(field)
        if value is None:
            # 尝试从嵌套结构提取
            if field == "author_name":
                value = tweet.get("author", {}).get("name", "") if isinstance(tweet.get("author"), dict) else ""
            elif field == "author_username":
                value = tweet.get("author", {}).get("username", "") if isinstance(tweet.get("author"), dict) else ""
            elif field == "has_media":
                value = bool(tweet.get("media") or tweet.get("photos") or tweet.get("videos"))
            else:
                value = ""
        flat[field] = value
    return flat


def _get_task_tweets(task_id: str) -> list[dict]:
    """获取任务推文列表，不存在则抛 404"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    tweets = task.get("tweets", [])
    if not tweets:
        raise HTTPException(status_code=204, detail="该任务暂无数据可供导出")
    return tweets


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
    tweets = _get_task_tweets(task_id)
    data = _build_csv(tweets)
    filename = f"xcrawl_{task_id[:8]}.csv"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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

    # 自动列宽
    col_widths = [20, 20, 16, 16, 60, 10, 10, 10, 10, 10, 50, 8, 10, 10]
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
    tweets = _get_task_tweets(task_id)
    data = _build_excel(tweets)
    filename = f"xcrawl_{task_id[:8]}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
