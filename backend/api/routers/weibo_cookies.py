"""
微博 Cookie 管理路由
GET    /api/v1/weibo-cookies          - 查看当前持久化 Cookie（脱敏）
POST   /api/v1/weibo-cookies          - 保存（JSON 数组 或 raw_string 原始字符串）
DELETE /api/v1/weibo-cookies          - 清空持久化 Cookie
POST   /api/v1/weibo-cookies/capture  - 从当前浏览器 tab 自动采集微博 Cookie
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/weibo-cookies", tags=["微博 Cookie 管理"])


class WeiboCookieSaveRequest(BaseModel):
    cookies: Optional[list[dict]] = None
    raw_string: Optional[str] = None


class WeiboCookieItem(BaseModel):
    name: str
    masked: str  # 脱敏 value


class WeiboCookiesResponse(BaseModel):
    cookies: list[WeiboCookieItem]
    has_login: bool
    count: int


@router.get("", response_model=WeiboCookiesResponse, summary="查看微博 Cookie（脱敏）")
async def get_weibo_cookies():
    from crawler.weibo.cookie_manager import load_cookies, has_weibo_login
    cookies = load_cookies()
    items = []
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        masked = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
        items.append(WeiboCookieItem(name=name, masked=masked))
    return WeiboCookiesResponse(
        cookies=items,
        has_login=has_weibo_login(cookies),
        count=len(items),
    )


@router.post("", summary="保存微博 Cookie")
async def save_weibo_cookies(req: WeiboCookieSaveRequest):
    from crawler.weibo.cookie_manager import normalize_cookies, save_cookies, has_weibo_login
    raw = req.raw_string or ""
    cookie_list = req.cookies or []
    if raw:
        normalized = normalize_cookies(raw)
    elif cookie_list:
        normalized = normalize_cookies(cookie_list)
    else:
        raise HTTPException(status_code=400, detail="请提供 cookies 数组或 raw_string 字符串")
    save_cookies(normalized)
    return {"saved": len(normalized), "has_login": has_weibo_login(normalized)}


@router.delete("", summary="清空微博 Cookie")
async def clear_weibo_cookies():
    from crawler.weibo.cookie_manager import clear_cookies
    clear_cookies()
    return {"cleared": True}


@router.post("/capture", summary="从浏览器采集微博 Cookie")
async def capture_weibo_cookies():
    from crawler.browser import get_browser
    from crawler.weibo.cookie_manager import capture_cookies_from_tab, save_cookies, has_weibo_login
    try:
        browser = get_browser()
        if not browser:
            raise HTTPException(status_code=503, detail="浏览器未启动，请先初始化浏览器")
        tab = browser.get_tab()
        captured = capture_cookies_from_tab(tab)
        if not captured:
            return {"captured": 0, "has_login": False, "message": "未捕获到微博 Cookie，请先在浏览器中登录微博"}
        save_cookies(captured)
        return {"captured": len(captured), "has_login": has_weibo_login(captured)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"采集微博 Cookie 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"采集失败: {str(e)}")
