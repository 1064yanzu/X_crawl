"""
Cookie 管理路由
GET    /api/v1/cookies          - 查看当前持久化 Cookie 列表（脱敏）
POST   /api/v1/cookies          - 手动保存 Cookie（JSON 数组或 document.cookie 字符串）
DELETE /api/v1/cookies          - 清空持久化 Cookie
POST   /api/v1/cookies/capture  - 从当前已启动的浏览器 tab 自动采集 Cookie
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from crawler.cookie_manager import (
    load_cookies,
    save_cookies,
    clear_cookies,
    normalize_cookies,
    capture_cookies_from_tab,
)
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


class CookieMasked(BaseModel):
    """对外展示时 value 脱敏"""
    name: str
    value_masked: str
    domain: str


class SaveCookiesRequest(BaseModel):
    """支持两种录入格式：JSON 数组 或 原始 document.cookie 字符串"""
    cookies: list[CookieItem] | None = Field(default=None, description="Cookie 字典列表")
    raw_string: str | None = Field(default=None, description="document.cookie 格式字符串")


class CookiesResponse(BaseModel):
    count: int
    cookies: list[CookieMasked]


class CaptureResponse(BaseModel):
    captured: int
    message: str


# ─── 工具函数 ──────────────────────────────────────────────────────────────

def _mask_value(value: str) -> str:
    """对 Cookie value 进行脱敏（只显示前 4 位和后 4 位）"""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}{'*' * min(len(value) - 8, 12)}{value[-4:]}"


def _to_masked(c: dict) -> CookieMasked:
    return CookieMasked(
        name=c.get("name", ""),
        value_masked=_mask_value(c.get("value", "")),
        domain=c.get("domain", ".x.com"),
    )


# ─── 路由 ──────────────────────────────────────────────────────────────────

@router.get("", response_model=CookiesResponse, summary="查看持久化 Cookie（脱敏）")
async def list_cookies():
    cookies = load_cookies()
    return CookiesResponse(
        count=len(cookies),
        cookies=[_to_masked(c) for c in cookies],
    )


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

    return CookiesResponse(
        count=len(normalized),
        cookies=[_to_masked(c) for c in normalized],
    )


@router.delete("", summary="清空持久化 Cookie")
async def delete_cookies():
    clear_cookies()
    return {"message": "已清空所有持久化 Cookie"}


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
        return CaptureResponse(captured=len(cookies), message=msg)

    except Exception as e:
        logger.error(f"从浏览器采集 Cookie 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"采集失败: {str(e)}")
