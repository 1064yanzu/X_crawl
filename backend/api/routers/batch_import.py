"""
批量导入任务路由
POST /api/v1/batch-import/parse - 解析上传的 CSV/Excel/TXT 文件，返回任务列表预览
"""
import csv
import io
import logging
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/batch-import", tags=["批量导入"])

VALID_PRODUCTS = {"top", "latest", "photos", "videos"}
VALID_PLATFORMS = {"x", "weibo"}


class ImportedTask(BaseModel):
    keyword: str
    max_count: int = 0
    product: Literal["Top", "Latest", "Photos", "Videos"] = "Top"
    platform: Literal["x", "weibo"] = "x"
    fetch_replies: bool = False
    reply_depth: int = 2
    max_replies_per_tweet: int = 0
    crawl_strategy: Literal["bfs", "dfs"] = "dfs"
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ParseResult(BaseModel):
    total: int
    tasks: list[ImportedTask]
    errors: list[str] = Field(default_factory=list)


# ── 类型转换工具 ──────────────────────────────────────────────


def _coerce_product(value: str) -> Literal["Top", "Latest", "Photos", "Videos"]:
    mapping = {"top": "Top", "latest": "Latest", "photos": "Photos", "videos": "Videos"}
    return mapping.get(str(value).strip().lower(), "Top")


def _coerce_platform(value: str) -> Literal["x", "weibo"]:
    return "weibo" if str(value).strip().lower() == "weibo" else "x"


def _coerce_bool(value: str) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes", "是", "开")


def _coerce_int(value: str, default: int = 0) -> int:
    try:
        return max(0, int(str(value).strip()))
    except (ValueError, TypeError):
        return default


# ── 文件解析逻辑 ─────────────────────────────────────────────


def _build_task_from_row(
    row_map: dict[str, str],
    default_platform: str,
    default_product: str,
    default_max_count: int,
    default_fetch_replies: bool,
) -> ImportedTask:
    """从一行列名→值映射构建 ImportedTask"""
    return ImportedTask(
        keyword=row_map.get("keyword", "").strip(),
        max_count=_coerce_int(
            row_map.get("max_count", str(default_max_count)), default_max_count
        ),
        product=_coerce_product(row_map.get("product", default_product)),
        platform=_coerce_platform(row_map.get("platform", default_platform)),
        fetch_replies=_coerce_bool(
            row_map.get("fetch_replies", str(default_fetch_replies))
        ),
        reply_depth=_coerce_int(row_map.get("reply_depth", "2"), 2) or 2,
        max_replies_per_tweet=_coerce_int(
            row_map.get("max_replies_per_tweet", "0"), 0
        ),
        crawl_strategy="dfs",
        start_date=row_map.get("start_date") or None,
        end_date=row_map.get("end_date") or None,
    )


def _make_simple_task(
    keyword: str,
    default_platform: str,
    default_product: str,
    default_max_count: int,
    default_fetch_replies: bool,
) -> ImportedTask:
    """仅有关键词时，使用全局默认参数创建任务"""
    return ImportedTask(
        keyword=keyword,
        max_count=default_max_count,
        product=_coerce_product(default_product),
        platform=_coerce_platform(default_platform),
        fetch_replies=default_fetch_replies,
    )


def _parse_csv_bytes(
    data: bytes,
    default_platform: str,
    default_product: str,
    default_max_count: int,
    default_fetch_replies: bool,
) -> ParseResult:
    """解析 CSV / TXT 字节数据"""
    text: str | None = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb2312"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return ParseResult(
            total=0, tasks=[], errors=["文件编码不支持，请使用 UTF-8 或 GBK 保存"]
        )

    tasks: list[ImportedTask] = []
    errors: list[str] = []

    # 探测是否为带表头 CSV
    sniffer_text = text[:2048]
    has_header = "keyword" in sniffer_text.lower().split("\n")[0] if sniffer_text else False

    if has_header:
        reader = csv.DictReader(io.StringIO(text))
        for idx, row in enumerate(reader, start=2):
            normalized = {
                k.strip().lower(): (v.strip() if v else "")
                for k, v in row.items()
                if k
            }
            keyword = normalized.get("keyword", "").strip()
            if not keyword:
                errors.append(f"第 {idx} 行: keyword 为空，已跳过")
                continue
            normalized["keyword"] = keyword
            tasks.append(
                _build_task_from_row(
                    normalized,
                    default_platform,
                    default_product,
                    default_max_count,
                    default_fetch_replies,
                )
            )
    else:
        # 无表头：每行第一个字段视为 keyword
        for idx, line in enumerate(text.splitlines(), start=1):
            keyword = line.strip().split(",")[0].strip().strip('"').strip("'")
            if not keyword:
                continue
            tasks.append(
                _make_simple_task(
                    keyword,
                    default_platform,
                    default_product,
                    default_max_count,
                    default_fetch_replies,
                )
            )

    return ParseResult(total=len(tasks), tasks=tasks, errors=errors)


def _parse_excel_bytes(
    data: bytes,
    default_platform: str,
    default_product: str,
    default_max_count: int,
    default_fetch_replies: bool,
) -> ParseResult:
    """解析 Excel 字节数据"""
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="缺少 openpyxl 依赖，请在后端执行: pip install openpyxl",
        )

    try:
        wb = openpyxl.load_workbook(
            io.BytesIO(data), read_only=True, data_only=True
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Excel 文件解析失败: {exc}")

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return ParseResult(total=0, tasks=[], errors=["Excel 文件为空"])

    tasks: list[ImportedTask] = []
    errors: list[str] = []

    first_row = [
        str(cell).strip().lower() if cell is not None else "" for cell in rows[0]
    ]
    has_header = "keyword" in first_row

    if has_header:
        headers = first_row
        for idx, row in enumerate(rows[1:], start=2):
            row_map = {
                headers[i]: (str(row[i]).strip() if row[i] is not None else "")
                for i in range(min(len(headers), len(row)))
            }
            keyword = row_map.get("keyword", "").strip()
            if not keyword:
                errors.append(f"第 {idx} 行: keyword 为空，已跳过")
                continue
            row_map["keyword"] = keyword
            tasks.append(
                _build_task_from_row(
                    row_map,
                    default_platform,
                    default_product,
                    default_max_count,
                    default_fetch_replies,
                )
            )
    else:
        for row in rows:
            if not row:
                continue
            keyword = str(row[0]).strip() if row[0] is not None else ""
            if not keyword:
                continue
            tasks.append(
                _make_simple_task(
                    keyword,
                    default_platform,
                    default_product,
                    default_max_count,
                    default_fetch_replies,
                )
            )

    return ParseResult(total=len(tasks), tasks=tasks, errors=errors)


# ── 路由 ─────────────────────────────────────────────────────


@router.post(
    "/parse",
    response_model=ParseResult,
    summary="解析批量导入文件",
    description=(
        "上传 CSV / TXT / Excel 文件，解析为任务列表预览。\n\n"
        "**支持的列名**（CSV 表头或 Excel 第一行）：\n"
        "- `keyword`（必须）：搜索关键词\n"
        "- `max_count`：采集数量上限（默认 0=不限）\n"
        "- `product`：内容类型 Top/Latest/Photos/Videos（默认 Top）\n"
        "- `platform`：平台 x/weibo（默认 x）\n"
        "- `fetch_replies`：是否抓取评论 true/false（默认 false）\n"
        "- `reply_depth`：评论深度 1-5（默认 2）\n"
        "- `max_replies_per_tweet`：每条推文最多评论数（默认 0=不限）\n"
        "- `start_date`：起始日期 YYYY-MM-DD（微博）\n"
        "- `end_date`：结束日期 YYYY-MM-DD（微博）\n\n"
        "若无表头，则视每行第一列/字段为 keyword，其余参数使用全局默认值。"
    ),
)
async def parse_import_file(
    file: UploadFile = File(..., description="CSV / TXT / Excel (.xlsx) 文件"),
    default_platform: str = Form(
        default="x", description="默认平台（文件中未指定时使用）"
    ),
    default_product: str = Form(
        default="Top", description="默认内容类型（文件中未指定时使用）"
    ),
    default_max_count: int = Form(
        default=0, description="默认采集数量（文件中未指定时使用）"
    ),
    default_fetch_replies: bool = Form(
        default=False, description="默认是否抓评论（文件中未指定时使用）"
    ),
) -> ParseResult:
    if not file.filename:
        raise HTTPException(status_code=400, detail="未上传文件")

    filename_lower = file.filename.lower()
    data = await file.read()

    if not data:
        raise HTTPException(status_code=400, detail="文件为空")

    if filename_lower.endswith((".csv", ".txt")):
        return _parse_csv_bytes(
            data, default_platform, default_product, default_max_count, default_fetch_replies
        )
    elif filename_lower.endswith((".xlsx", ".xls")):
        return _parse_excel_bytes(
            data, default_platform, default_product, default_max_count, default_fetch_replies
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file.filename}，请上传 CSV、TXT 或 Excel 文件",
        )
