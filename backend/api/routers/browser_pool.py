"""
浏览器池状态路由

GET  /api/v1/browser-pool/status  — 查看浏览器池实时状态
PUT  /api/v1/browser-pool/resize  — 动态调整并发数
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import settings
from api.services.settings_db import set_settings_batch
from crawler.browser_pool import get_browser_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/browser-pool", tags=["浏览器池"])


# ─── 响应模型 ───────────────────────────────────────────────

class SlotInfo(BaseModel):
    """单个并发槽位的信息"""
    slot_id: int
    platforms: dict[str, str] = Field(
        default_factory=dict,
        description="当前占用此 slot 的 { platform: task_id }",
    )
    alive: bool = Field(description="浏览器实例是否存活")


class BrowserPoolStatusResponse(BaseModel):
    """浏览器池完整状态"""
    max_size: int = Field(description="并发上限")
    total_slots: int = Field(description="已创建的浏览器实例总数")
    active_slots: int = Field(description="当前有任务占用的槽位数")
    idle_slots: int = Field(description="空闲（无任务占用）的槽位数")
    slots: list[SlotInfo] = Field(default_factory=list)


class ResizeRequest(BaseModel):
    """调整并发数请求"""
    max_size: int = Field(ge=1, le=10, description="新的并发上限，范围 1–10")


class ResizeResponse(BaseModel):
    """调整并发数响应"""
    message: str
    previous_max_size: int
    new_max_size: int


# ─── 端点 ────────────────────────────────────────────────────

@router.get(
    "/status",
    response_model=BrowserPoolStatusResponse,
    summary="查看浏览器池状态",
    description="返回浏览器池的实时状态，包含各 slot 的平台占用和存活指标。",
)
async def get_pool_status() -> BrowserPoolStatusResponse:
    pool = get_browser_pool()
    raw = pool.status()

    slots = [
        SlotInfo(
            slot_id=s["slot_id"],
            platforms=s["platforms"],
            alive=s["alive"],
        )
        for s in raw["slots"]
    ]

    active = sum(1 for s in slots if s.platforms)

    return BrowserPoolStatusResponse(
        max_size=raw["max_size"],
        total_slots=raw["total_slots"],
        active_slots=active,
        idle_slots=raw["total_slots"] - active,
        slots=slots,
    )


@router.put(
    "/resize",
    response_model=ResizeResponse,
    summary="动态调整并发数",
    description=(
        "实时调整浏览器池并发上限。同时会更新配置并持久化到数据库，重启后仍生效。\n\n"
        "**注意**：缩减时不会关闭已在运行的实例，只会阻止更多实例被创建。"
    ),
)
async def resize_pool(req: ResizeRequest) -> ResizeResponse:
    pool = get_browser_pool()
    previous = pool.max_size

    if req.max_size == previous:
        return ResizeResponse(
            message="并发上限未变化",
            previous_max_size=previous,
            new_max_size=previous,
        )

    # 1. 更新池大小
    pool.resize(req.max_size)

    # 2. 同步更新内存中的 settings
    settings.crawler_max_concurrent_tasks = req.max_size

    # 3. 持久化到数据库
    try:
        set_settings_batch({"crawler_max_concurrent_tasks": req.max_size})
    except Exception as e:
        logger.warning(f"[BrowserPool] 持久化并发设置失败: {e}")

    direction = "增加" if req.max_size > previous else "减少"
    logger.info(
        f"[BrowserPool] 并发上限已{direction}: {previous} → {req.max_size}"
    )

    return ResizeResponse(
        message=f"并发上限已从 {previous} 调整为 {req.max_size}",
        previous_max_size=previous,
        new_max_size=req.max_size,
    )
