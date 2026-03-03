"""
Cookie 管理路由
GET    /api/v1/cookies                   - 查看当前持久化 Cookie（以账号为单位分组展示）
POST   /api/v1/cookies                   - 手动保存 Cookie（JSON 数组或 document.cookie 字符串）
DELETE /api/v1/cookies                   - 清空持久化 Cookie
DELETE /api/v1/cookies/{cookie_name}     - 删除指定名称的 Cookie
POST   /api/v1/cookies/capture           - 从当前已启动的浏览器 tab 自动采集 Cookie
"""
import json
import logging
from typing import Any, Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from crawler.cookie_manager import (
    load_cookies,
    save_cookies,
    clear_cookies,
    normalize_cookies,
    capture_cookies_from_tab,
)
from crawler.cookie_account_sync import sync_cookies_to_pool, remove_account_from_pool
from crawler.browser import get_browser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/cookies", tags=["Cookie 管理"])


# ─── 数据模型 ──────────────────────────────────────────────────────────────

class CookieItem(BaseModel):
    name: str
    value: str = ""
    domain: str = ".x.com"
    path: str = "/"
    secure: bool = False
    httpOnly: bool = False

# 认证关键 Cookie 名称
_AUTH_CRITICAL_COOKIES = {"auth_token", "twid", "ct0"}


class CookieMasked(BaseModel):
    """对外展示时 value 脱敏，并带上分类标记"""
    name: str
    value_masked: str
    domain: str
    category: str  # "auth" | "session" | "other"
    is_critical: bool  # 是否为登录必须 Cookie


class CookieAccount(BaseModel):
    """以账号为单位的 Cookie 分组"""
    user_id: str  # 从 twid 提取的用户 ID，无法提取时为 "unknown"
    cookie_count: int
    has_login: bool  # 是否包含完整登录凭证
    cookies: list[CookieMasked]


class SaveCookiesRequest(BaseModel):
    """支持两种录入格式：JSON 数组 或 原始 document.cookie 字符串"""
    cookies: list[CookieItem] | None = Field(default=None, description="Cookie 字典列表")
    raw_string: str | None = Field(default=None, description="document.cookie 格式字符串")


class CookiesResponse(BaseModel):
    count: int
    has_login: bool = False
    accounts: list[CookieAccount] = []  # 以账号为单位分组
    cookies: list[CookieMasked] = []  # 扁平列表（兼容旧调用）


class CaptureResponse(BaseModel):
    captured: int
    message: str


# ─── 工具函数 ──────────────────────────────────────────────────────────────

def _mask_value(value: str) -> str:
    """对 Cookie value 进行脱敏（只显示前 4 位和后 4 位）"""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}{'*' * min(len(value) - 8, 12)}{value[-4:]}"


def _categorize_cookie(name: str) -> str:
    """将 Cookie 按功能分类"""
    if name in _AUTH_CRITICAL_COOKIES:
        return "auth"
    if name in {"_twitter_sess", "kdt", "guest_id", "guest_id_marketing", "guest_id_ads", "gt"}:
        return "session"
    return "other"


def _to_masked(c: dict) -> CookieMasked:
    name = c.get("name", "")
    return CookieMasked(
        name=name,
        value_masked=_mask_value(c.get("value", "")),
        domain=c.get("domain", ".x.com"),
        category=_categorize_cookie(name),
        is_critical=name in _AUTH_CRITICAL_COOKIES,
    )


def _extract_user_id(cookies: list[dict]) -> str:
    """从 twid Cookie 中提取用户 ID。twid 格式为 u%3D{user_id}"""
    for c in cookies:
        if c.get("name") == "twid":
            val = unquote(c.get("value", ""))  # u%3D12345 -> u=12345
            if val.startswith("u="):
                return val[2:]
            return val
    return "unknown"


def _build_response(cookies: list[dict]) -> CookiesResponse:
    """构建以账号为单位分组的响应。全局 Cookie 视为单个账号。"""
    masked = [_to_masked(c) for c in cookies]
    names = {c.get("name", "") for c in cookies}
    has_login = "auth_token" in names and "twid" in names

    accounts: list[CookieAccount] = []
    if cookies:
        user_id = _extract_user_id(cookies)
        accounts.append(CookieAccount(
            user_id=user_id,
            cookie_count=len(cookies),
            has_login=has_login,
            cookies=masked,
        ))

    return CookiesResponse(
        count=len(cookies),
        has_login=has_login,
        accounts=accounts,
        cookies=masked,
    )


# ─── 路由 ──────────────────────────────────────────────────────────────────

@router.get("", response_model=CookiesResponse, summary="查看持久化 Cookie（以账号分组）")
async def list_cookies():
    cookies = load_cookies()
    return _build_response(cookies)


@router.post("", response_model=CookiesResponse, summary="手动保存 Cookie")
async def upsert_cookies(req: SaveCookiesRequest):
    """
    接受两种格式：
    1. `cookies`：[{"name": "auth_token", "value": "xxx", "domain": ".x.com"}]
    2. `raw_string`："auth_token=xxx; twid=yyy"
    """
    if req.cookies is not None:
        raw: Any = [c.model_dump() for c in req.cookies]
    elif req.raw_string is not None:
        raw = req.raw_string
    else:
        raise HTTPException(status_code=422, detail="必须提供 cookies 或 raw_string 之一")

    normalized = normalize_cookies(raw)
    if not normalized:
        raise HTTPException(status_code=422, detail="解析后 Cookie 为空，请检查格式")

    try:
        save_cookies(normalized)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入 Cookie 失败: {e}")

    # 自动同步到账号池
    sync_cookies_to_pool(normalized)

    return _build_response(normalized)


@router.delete("", summary="清空持久化 Cookie")
async def delete_cookies():
    # 先读取当前 Cookie 以便同步移除账号
    old_cookies = load_cookies()
    clear_cookies()
    # 同步移除账号池中对应账号
    if old_cookies:
        remove_account_from_pool(old_cookies)
    return {"message": "已清空所有持久化 Cookie"}


@router.delete("/{cookie_name}", response_model=CookiesResponse, summary="删除指定名称的 Cookie")
async def delete_single_cookie(
    cookie_name: str,
    domain: Optional[str] = Query(default=None, description="可选：指定 domain 精确匹配"),
):
    """
    删除指定 name 的 Cookie。
    若同名 Cookie 存在多个 domain，可通过 domain 参数精确指定。
    若不指定 domain，则删除所有同名 Cookie。
    """
    cookies = load_cookies()
    original_count = len(cookies)

    if domain:
        remaining = [c for c in cookies if not (c.get("name") == cookie_name and c.get("domain") == domain)]
    else:
        remaining = [c for c in cookies if c.get("name") != cookie_name]

    if len(remaining) == original_count:
        raise HTTPException(status_code=404, detail=f"Cookie '{cookie_name}' 不存在")

    deleted_count = original_count - len(remaining)
    save_cookies(remaining)
    logger.info(f"已删除 Cookie: {cookie_name}（{deleted_count} 条）")

    # 同步到账号池（可能登录态已失效，刷新状态）
    sync_cookies_to_pool(remaining)

    return _build_response(remaining)


@router.post("/capture", response_model=CaptureResponse, summary="从浏览器自动采集 Cookie")
async def capture_from_browser():
    """
    需要浏览器已经启动（用户已通过 X/Twitter 登录）。
    自动从当前浏览器 tab 采集 Cookie 并持久化。
    """
    try:
        browser = get_browser()
        # 使用现有 tab 或新建一个，访问 x.com 以确保 Cookie 被加载
        tab = browser.get_tab()
        if tab is None:
            tab = browser.new_tab()

        # 若当前 tab 不在 x.com，先导航过去
        if "x.com" not in (tab.url or ""):
            tab.get("https://x.com", timeout=20)

        cookies = capture_cookies_from_tab(tab)

        if not cookies:
            return CaptureResponse(captured=0, message="未采集到任何 Cookie，请确认浏览器已登录 X")

        # 只统计关键 Cookie
        key_names = {c.get("name") for c in cookies}
        has_auth = "auth_token" in key_names and "twid" in key_names
        msg = (
            f"✅ 成功采集 {len(cookies)} 条 Cookie，登录状态有效"
            if has_auth
            else f"⚠️ 采集了 {len(cookies)} 条 Cookie，但未检测到 auth_token/twid，请先登录 X"
        )

        # 自动同步到账号池
        sync_cookies_to_pool(cookies)

        return CaptureResponse(captured=len(cookies), message=msg)

    except Exception as e:
        logger.error(f"从浏览器采集 Cookie 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"采集失败: {str(e)}")


# ─── 导出 ──────────────────────────────────────────────────────────────────

class ExportCookiesResponse(BaseModel):
    count: int
    cookies: list[dict]
    format: str


@router.get("/export", summary="导出 Cookie（完整值, JSON 格式）")
async def export_cookies_json():
    """
    导出完整 Cookie 列表（不脱敏），以 JSON 文件形式下载。
    可用于备份或迁移到其他环境。
    """
    cookies = load_cookies()
    if not cookies:
        raise HTTPException(status_code=404, detail="没有可导出的 Cookie")

    content = json.dumps(cookies, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="xcrawl-cookies.json"',
        },
    )


@router.get("/export/string", summary="导出 Cookie（document.cookie 字符串格式）")
async def export_cookies_string():
    """
    导出为 document.cookie 格式字符串（name=value; name=value）。
    方便直接粘贴到浏览器控制台或其他工具中使用。
    """
    cookies = load_cookies()
    if not cookies:
        raise HTTPException(status_code=404, detail="没有可导出的 Cookie")

    cookie_str = "; ".join(
        f"{c.get('name', '')}={c.get('value', '')}" for c in cookies if c.get("name")
    )
    return Response(
        content=cookie_str,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="xcrawl-cookies.txt"',
        },
    )
