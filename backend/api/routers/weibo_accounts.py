"""
微博账号池管理路由

GET    /api/v1/weibo-accounts                    - 列表（Cookie 脱敏）
POST   /api/v1/weibo-accounts                    - 添加账号
PUT    /api/v1/weibo-accounts/{account_id}       - 更新（alias / enabled）
DELETE /api/v1/weibo-accounts/{account_id}       - 删除
POST   /api/v1/weibo-accounts/{account_id}/validate - 验证账号登录状态
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/weibo-accounts", tags=["微博账号池管理"])


# ─── 数据模型 ───────────────────────────────────────────────────────────────

class AddWeiboAccountRequest(BaseModel):
    alias: str = Field(..., description="账号备注名")
    cookies: Optional[list[dict]] = Field(default=None, description="Cookie 列表")
    raw_cookie_string: Optional[str] = Field(
        default=None, description="可选：key=val; key2=val2 格式字符串"
    )


class UpdateWeiboAccountRequest(BaseModel):
    alias: Optional[str] = Field(default=None, description="新备注名")
    enabled: Optional[bool] = Field(default=None, description="是否启用")


class WeiboAccountOut(BaseModel):
    account_id: str
    alias: str
    enabled: bool
    is_valid: bool
    is_rate_limited: bool
    cookie_count: int
    use_count: int
    fail_count: int
    added_at: float
    last_used_at: float
    last_validated_at: float
    rate_reset_at: float


# ─── 工具函数 ───────────────────────────────────────────────────────────────

def _to_out(acc) -> WeiboAccountOut:
    return WeiboAccountOut(
        account_id=acc.account_id,
        alias=acc.alias,
        enabled=acc.enabled,
        is_valid=acc.is_valid,
        is_rate_limited=acc.is_rate_limited,
        cookie_count=acc.cookie_count,
        use_count=acc.use_count,
        fail_count=acc.fail_count,
        added_at=acc.added_at,
        last_used_at=acc.last_used_at,
        last_validated_at=acc.last_validated_at,
        rate_reset_at=acc.rate_reset_at,
    )


# ─── 路由 ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[WeiboAccountOut], summary="列出所有微博账号（脱敏）")
async def list_weibo_accounts():
    from crawler.weibo.account_pool import get_weibo_pool
    pool = get_weibo_pool()
    return [_to_out(a) for a in pool.list_accounts()]


@router.post("", response_model=WeiboAccountOut, summary="添加微博账号")
async def add_weibo_account(req: AddWeiboAccountRequest):
    from crawler.weibo.account_pool import get_weibo_pool
    from crawler.weibo.cookie_manager import normalize_cookies

    pool = get_weibo_pool()

    if req.raw_cookie_string:
        cookies = normalize_cookies(req.raw_cookie_string)
    elif req.cookies:
        cookies = normalize_cookies(req.cookies)
    else:
        raise HTTPException(status_code=400, detail="请提供 cookies 或 raw_cookie_string")

    if not cookies:
        raise HTTPException(status_code=422, detail="解析后 Cookie 为空，请检查格式")

    entry = pool.add_account(alias=req.alias, cookies=cookies)
    logger.info(f"微博账号 {req.alias!r} 已添加/更新，共 {len(cookies)} 条 Cookie")
    return _to_out(entry)


@router.put("/{account_id}", response_model=WeiboAccountOut, summary="更新微博账号信息")
async def update_weibo_account(account_id: str, req: UpdateWeiboAccountRequest):
    from crawler.weibo.account_pool import get_weibo_pool
    pool = get_weibo_pool()
    updated = pool.update_account(account_id, alias=req.alias, enabled=req.enabled)
    if not updated:
        raise HTTPException(status_code=404, detail=f"微博账号 {account_id} 不存在")
    return _to_out(updated)


@router.delete("/{account_id}", summary="删除微博账号")
async def delete_weibo_account(account_id: str):
    from crawler.weibo.account_pool import get_weibo_pool
    pool = get_weibo_pool()
    ok = pool.remove_account(account_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"微博账号 {account_id} 不存在")
    return {"message": f"微博账号 {account_id} 已删除"}


@router.post("/{account_id}/validate", response_model=WeiboAccountOut, summary="验证微博账号登录状态")
async def validate_weibo_account(account_id: str):
    from crawler.weibo.account_pool import get_weibo_pool
    from crawler.weibo.auth import ensure_weibo_login

    pool = get_weibo_pool()
    account = pool.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"微博账号 {account_id} 不存在")

    try:
        from crawler.browser import get_new_tab
        tab = get_new_tab()
        try:
            ok = ensure_weibo_login(tab, account_cookies=account.cookies)
            if ok:
                pool.mark_account_validated(account_id)
                logger.info(f"微博账号 {account.alias!r} 验证成功")
            else:
                pool.mark_account_invalid(account_id)
                logger.warning(f"微博账号 {account.alias!r} 验证失败")
        finally:
            try:
                tab.close()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"验证微博账号 {account_id} 时出错: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")

    updated = pool.get_account(account_id)
    if not updated:
        raise HTTPException(status_code=404, detail="账号已被删除")
    return _to_out(updated)
