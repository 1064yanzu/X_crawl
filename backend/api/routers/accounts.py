"""
账号池管理路由

GET    /api/v1/accounts                    - 列表（Cookie 字段脱敏，只返回数量和 domain）
POST   /api/v1/accounts                    - 添加账号（body: alias + cookies JSON）
PUT    /api/v1/accounts/{account_id}       - 更新（alias / enabled）
DELETE /api/v1/accounts/{account_id}       - 删除
POST   /api/v1/accounts/{account_id}/validate - 验证账号是否有效（注入 tab 检查登录）
GET    /api/v1/accounts/interval-suggestion   - 返回当前最优动态间隔建议
"""
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from crawler.account_pool import get_pool, compute_dynamic_interval, AccountEntry
from crawler.cookie_manager import normalize_cookies

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/accounts", tags=["账号池管理"])


# ─── 数据模型 ───────────────────────────────────────────────────────────────

class CookieItemIn(BaseModel):
    name: str
    value: str = ""
    domain: str = ".x.com"
    path: str = "/"
    secure: bool = False
    httpOnly: bool = False


class AddAccountRequest(BaseModel):
    alias: str = Field(..., description="账号备注名，如 @user1")
    cookies: list[CookieItemIn] = Field(..., description="Cookie 列表")
    raw_cookie_string: Optional[str] = Field(
        default=None, description="可选：document.cookie 格式字符串，优先于 cookies 字段"
    )


class UpdateAccountRequest(BaseModel):
    alias: Optional[str] = Field(default=None, description="新备注名")
    enabled: Optional[bool] = Field(default=None, description="是否启用")


class AccountOut(BaseModel):
    """对外展示的账号信息（Cookie 完全脱敏，只显示数量和 domain）"""
    account_id: str
    alias: str
    enabled: bool
    is_valid: bool
    is_rate_limited: bool
    cookie_count: int
    cookie_domains: list[str]
    use_count: int
    fail_count: int
    added_at: float
    last_used_at: float
    last_validated_at: float
    rate_reset_at: float


class IntervalSuggestion(BaseModel):
    """动态间隔建议"""
    active_account_count: int
    total_account_count: int
    search_interval_min: float
    search_interval_max: float
    search_safe_interval: float
    tweet_detail_interval_min: float
    tweet_detail_interval_max: float
    tweet_detail_safe_interval: float
    note: str


# ─── 工具函数 ───────────────────────────────────────────────────────────────

def _to_account_out(acc: AccountEntry) -> AccountOut:
    return AccountOut(
        account_id=acc.account_id,
        alias=acc.alias,
        enabled=acc.enabled,
        is_valid=acc.is_valid,
        is_rate_limited=acc.is_rate_limited,
        cookie_count=acc.cookie_count,
        cookie_domains=acc.cookie_domains,
        use_count=acc.use_count,
        fail_count=acc.fail_count,
        added_at=acc.added_at,
        last_used_at=acc.last_used_at,
        last_validated_at=acc.last_validated_at,
        rate_reset_at=acc.rate_reset_at,
    )


# ─── 路由 ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AccountOut], summary="列出所有账号（脱敏）")
async def list_accounts():
    """返回所有账号，Cookie 完全脱敏，只显示数量和 domain。"""
    pool = get_pool()
    return [_to_account_out(a) for a in pool.list_accounts()]


@router.post("/reload", summary="从文件重新加载账号池")
async def reload_accounts():
    """从磁盘文件重新加载账号池（用于手动修改文件后同步到内存）"""
    pool = get_pool()
    pool.reload()
    return {"message": f"账号池已重新加载，当前 {len(pool.list_accounts())} 个账号"}


@router.post("", response_model=AccountOut, summary="添加账号")
async def add_account(req: AddAccountRequest):
    """
    添加新账号或更新同名账号的 Cookie。
    支持两种 Cookie 输入方式：
    1. `raw_cookie_string`：document.cookie 格式字符串（优先）
    2. `cookies`：Cookie 字典列表
    """
    pool = get_pool()

    if req.raw_cookie_string:
        cookies = normalize_cookies(req.raw_cookie_string)
    else:
        cookies = normalize_cookies([c.model_dump() for c in req.cookies])

    if not cookies:
        raise HTTPException(status_code=422, detail="解析后 Cookie 为空，请检查格式")

    entry = pool.add_account(alias=req.alias, cookies=cookies)
    logger.info(f"账号 {req.alias!r} 已添加/更新，共 {len(cookies)} 条 Cookie")
    return _to_account_out(entry)


@router.put("/{account_id}", response_model=AccountOut, summary="更新账号信息")
async def update_account(account_id: str, req: UpdateAccountRequest):
    pool = get_pool()
    updated = pool.update_account(account_id, alias=req.alias, enabled=req.enabled)
    if not updated:
        raise HTTPException(status_code=404, detail=f"账号 {account_id} 不存在")
    return _to_account_out(updated)


@router.delete("/{account_id}", summary="删除账号")
async def delete_account(account_id: str):
    pool = get_pool()
    ok = pool.remove_account(account_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"账号 {account_id} 不存在")
    return {"message": f"账号 {account_id} 已删除"}


@router.post("/{account_id}/reset-valid", response_model=AccountOut, summary="恢复账号有效状态")
async def reset_account_valid(account_id: str):
    """将账号的 is_valid 恢复为 True（用于修复因 Cloudflare challenge 等非账号原因被误标无效的账号）"""
    pool = get_pool()
    ok = pool.reset_account_valid(account_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"账号 {account_id} 不存在")
    updated = pool.get_account(account_id)
    return _to_account_out(updated)


@router.post("/{account_id}/validate", response_model=AccountOut, summary="验证账号登录状态")
async def validate_account(account_id: str):
    """
    注入账号 Cookie 到当前浏览器 tab 并验证登录状态。
    需要浏览器已启动（先用搜索任务初始化浏览器，或手动启动调试端口）。
    """
    pool = get_pool()
    account = pool.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"账号 {account_id} 不存在")

    try:
        from crawler.browser import get_new_tab
        from crawler.auth import ensure_login_with_pool
        tab = get_new_tab()
        try:
            ok = ensure_login_with_pool(tab, account)
        finally:
            try:
                tab.close()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"验证账号 {account_id} 时出错: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")

    # 重新获取最新状态
    updated = pool.get_account(account_id)
    if not updated:
        raise HTTPException(status_code=404, detail=f"账号已被删除")
    return _to_account_out(updated)


@router.get("/interval-suggestion", response_model=IntervalSuggestion, summary="获取当前动态间隔建议")
async def get_interval_suggestion():
    """
    根据活跃账号数返回最优请求间隔建议。
    可用于前端显示或调试确认多账号生效情况。
    """
    pool = get_pool()
    active = pool.get_active_account_count()
    total = pool.total_count()

    s_min, s_max, s_factor = compute_dynamic_interval("search")
    td_min, td_max, td_factor = compute_dynamic_interval("tweet_detail")

    if active > 1:
        note = (
            f"当前 {active} 个活跃账号，间隔已缩短为单账号的 1/{active}。"
            f"搜索接口建议间隔约 {(s_min + s_max) / 2:.1f}s，"
            f"评论接口建议间隔约 {(td_min + td_max) / 2:.1f}s。"
        )
    elif active == 1:
        note = f"当前 1 个账号，搜索建议间隔约 {(s_min + s_max) / 2:.1f}s（单账号安全系数 {s_factor}x）。"
    else:
        note = "当前无活跃账号，将使用配置文件中的默认间隔。"

    return IntervalSuggestion(
        active_account_count=active,
        total_account_count=total,
        search_interval_min=round(s_min, 2),
        search_interval_max=round(s_max, 2),
        search_safe_interval=round((s_min + s_max) / 2, 2),
        tweet_detail_interval_min=round(td_min, 2),
        tweet_detail_interval_max=round(td_max, 2),
        tweet_detail_safe_interval=round((td_min + td_max) / 2, 2),
        note=note,
    )
