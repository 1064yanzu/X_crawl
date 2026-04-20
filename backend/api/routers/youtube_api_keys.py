"""
YouTube API Key 池管理路由

- GET    /api/v1/youtube-api-keys             列出所有 Key（API Key 脱敏）
- POST   /api/v1/youtube-api-keys             新增 Key
- PUT    /api/v1/youtube-api-keys/{key_id}    更新 alias / enabled / daily_quota_limit
- DELETE /api/v1/youtube-api-keys/{key_id}    删除
- POST   /api/v1/youtube-api-keys/{key_id}/validate  发送一次轻量请求验证 Key
- GET    /api/v1/youtube-api-keys/quota       当日配额汇总
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from crawler.youtube import api_client, api_key_pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/youtube-api-keys", tags=["YouTube Key 管理"])


# ─── 请求 / 响应模型 ─────────────────────────────────────────────────────────


class YouTubeKeyOut(BaseModel):
    key_id: str
    alias: str
    api_key_masked: str
    enabled: bool
    daily_quota_limit: int
    quota_used_today: int
    quota_remaining: int
    quota_reset_at: Optional[str] = None
    status: str
    last_used_at: Optional[str] = None
    last_validated_at: Optional[str] = None
    fail_count: int
    last_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AddKeyRequest(BaseModel):
    alias: str = Field(..., description="显示备注名")
    api_key: str = Field(..., description="YouTube Data API v3 Key 明文")
    enabled: bool = Field(default=True, description="是否启用")


class UpdateKeyRequest(BaseModel):
    alias: Optional[str] = None
    enabled: Optional[bool] = None
    daily_quota_limit: Optional[int] = Field(default=None, ge=100, le=1000000)


class ValidateResponse(BaseModel):
    key_id: str
    ok: bool
    status: int
    reason: Optional[str] = None
    message: str


class QuotaSummary(BaseModel):
    total_keys: int
    active_keys: int
    exhausted_keys: int
    invalid_keys: int
    total_daily_limit: int
    total_used_today: int
    total_remaining_today: int
    earliest_reset_at: Optional[str] = None
    keys: list[YouTubeKeyOut]


def _to_out(public_dict: dict) -> YouTubeKeyOut:
    return YouTubeKeyOut(**public_dict)


# ─── 路由 ─────────────────────────────────────────────────────────────────


@router.get("", response_model=list[YouTubeKeyOut], summary="列出 YouTube API Key")
async def list_keys() -> list[YouTubeKeyOut]:
    pool = api_key_pool.get_pool()
    return [_to_out(k.to_public_dict()) for k in pool.list_keys()]


@router.get("/quota", response_model=QuotaSummary, summary="YouTube 配额汇总")
async def get_quota() -> QuotaSummary:
    pool = api_key_pool.get_pool()
    data = pool.summary()
    data["keys"] = [YouTubeKeyOut(**k) for k in data.get("keys", [])]
    return QuotaSummary(**data)


@router.post("", response_model=YouTubeKeyOut, summary="新增 YouTube API Key")
async def add_key(req: AddKeyRequest) -> YouTubeKeyOut:
    pool = api_key_pool.get_pool()
    try:
        new_key = pool.add_key(alias=req.alias, api_key=req.api_key, enabled=req.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_out(new_key.to_public_dict())


@router.put("/{key_id}", response_model=YouTubeKeyOut, summary="更新 YouTube API Key")
async def update_key(key_id: str, req: UpdateKeyRequest) -> YouTubeKeyOut:
    pool = api_key_pool.get_pool()
    updated = pool.update_key(
        key_id,
        alias=req.alias,
        enabled=req.enabled,
        daily_quota_limit=req.daily_quota_limit,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="未找到指定 Key")
    return _to_out(updated.to_public_dict())


@router.delete("/{key_id}", summary="删除 YouTube API Key")
async def delete_key(key_id: str) -> dict:
    pool = api_key_pool.get_pool()
    ok = pool.delete_key(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到指定 Key")
    return {"message": "Key 已删除", "key_id": key_id}


@router.post("/{key_id}/validate", response_model=ValidateResponse, summary="验证 YouTube API Key")
async def validate_key_endpoint(key_id: str) -> ValidateResponse:
    pool = api_key_pool.get_pool()
    key = pool.get(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="未找到指定 Key")

    result = api_client.validate_key(key.api_key)
    if result.get("ok"):
        pool.mark_validated(key_id)
    else:
        reason = result.get("reason") or "unknown"
        if result.get("status") == 400 and reason == "keyInvalid":
            pool.mark_invalid(key_id, reason=reason)
        else:
            pool.record_failure(key_id, reason=reason)
    return ValidateResponse(
        key_id=key_id,
        ok=bool(result.get("ok")),
        status=int(result.get("status") or 0),
        reason=result.get("reason"),
        message=result.get("message") or "",
    )
