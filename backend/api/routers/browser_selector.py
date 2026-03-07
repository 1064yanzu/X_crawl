"""
浏览器管理路由

GET   /api/v1/browsers            列出所有检测到的浏览器
GET   /api/v1/browsers/selected   获取当前选中的浏览器
PUT   /api/v1/browsers/select     选择要使用的浏览器（持久化）
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from crawler.auth import get_login_diagnostics
from crawler.browser import get_browser_session_info
from crawler.browser_detector import detect_all_browsers, get_browser_by_id, _get_platform
from api.services.settings_db import get_setting, set_setting
from config import settings

router = APIRouter(prefix="/api/v1/browsers", tags=["浏览器管理"])


class BrowserInfo(BaseModel):
    """单个浏览器信息"""
    id: str = Field(description="浏览器标识符")
    name: str = Field(description="浏览器显示名称")
    engine: str = Field(description="内核类型：chromium / firefox / other")
    compatible: bool = Field(description="是否与 DrissionPage 兼容（仅 Chromium 内核兼容）")
    path: str = Field(description="可执行文件路径")
    user_data_path: Optional[str] = Field(default=None, description="用户数据目录路径")
    selected: bool = Field(default=False, description="是否为当前选中的浏览器")


class BrowserListResponse(BaseModel):
    """浏览器列表响应"""
    platform: str = Field(description="当前操作系统平台")
    count: int = Field(description="检测到的浏览器数量")
    selected_id: str = Field(description="当前选中的浏览器 ID（空字符串表示自动检测）")
    session_mode: str = Field(default="unknown", description="当前实际会话模式：attached_browser / crawler_profile / unknown")
    effective_user_data_path: Optional[str] = Field(default=None, description="当前实际使用的用户数据目录")
    crawler_profile_path: str = Field(default="", description="爬虫专用持久化 Profile 路径")
    crawler_profile_exists: bool = Field(default=False, description="爬虫专用 Profile 目录是否存在")
    crawler_profile_initialized: bool = Field(default=False, description="爬虫专用 Profile 是否已有初始化内容")
    browser_alive: bool = Field(default=False, description="当前浏览器实例是否存活")
    headless: bool = Field(default=False, description="当前浏览器是否运行于无头模式")
    last_login_check_at: Optional[str] = Field(default=None, description="最近一次登录检测时间")
    last_login_success_at: Optional[str] = Field(default=None, description="最近一次登录通过时间")
    last_login_failure_reason: Optional[str] = Field(default=None, description="最近一次登录失败原因")
    last_page_state: Optional[str] = Field(default=None, description="最近一次登录检测时的页面状态")
    browsers: list[BrowserInfo]


class SelectBrowserRequest(BaseModel):
    """选择浏览器请求"""
    browser_id: str = Field(description="要选择的浏览器 ID，传空字符串表示恢复自动检测")


class SelectBrowserResponse(BaseModel):
    """选择浏览器响应"""
    message: str
    browser_id: str
    browser_name: Optional[str] = None
    restart_required: bool = Field(
        default=True,
        description="是否需要重启浏览器实例才能生效"
    )


def _get_selected_id() -> str:
    """获取用户选择的浏览器 ID"""
    val = get_setting("browser_selected_id")
    if val and isinstance(val, str):
        return val
    return settings.browser_selected_id or ""


@router.get(
    "",
    response_model=BrowserListResponse,
    summary="列出所有检测到的浏览器",
    description="自动检测当前系统已安装的所有主流浏览器，返回名称、路径、兼容性等信息。",
)
async def list_browsers() -> BrowserListResponse:
    browsers_raw = detect_all_browsers()
    selected_id = _get_selected_id()
    session_info = get_browser_session_info()
    login_info = get_login_diagnostics()

    browsers = [
        BrowserInfo(
            id=b["id"],
            name=b["name"],
            engine=b["engine"],
            compatible=b["compatible"],
            path=b["path"],
            user_data_path=b.get("user_data_path"),
            selected=(b["id"] == selected_id),
        )
        for b in browsers_raw
    ]

    return BrowserListResponse(
        platform=_get_platform(),
        count=len(browsers),
        selected_id=selected_id,
        session_mode=str(session_info.get("session_mode") or "unknown"),
        effective_user_data_path=session_info.get("effective_user_data_path"),
        crawler_profile_path=str(session_info.get("crawler_profile_path") or ""),
        crawler_profile_exists=bool(session_info.get("crawler_profile_exists")),
        crawler_profile_initialized=bool(session_info.get("crawler_profile_initialized")),
        browser_alive=bool(session_info.get("browser_alive")),
        headless=bool(session_info.get("headless")),
        last_login_check_at=login_info.get("last_login_check_at"),
        last_login_success_at=login_info.get("last_login_success_at"),
        last_login_failure_reason=login_info.get("last_login_failure_reason"),
        last_page_state=login_info.get("last_page_state"),
        browsers=browsers,
    )


@router.get(
    "/selected",
    response_model=BrowserInfo,
    summary="获取当前选中的浏览器信息",
    description="返回用户当前选中的浏览器详情。若未选择或选择的浏览器已卸载，返回自动检测的首个兼容浏览器。",
    responses={404: {"description": "未检测到任何兼容浏览器"}},
)
async def get_selected_browser() -> BrowserInfo:
    selected_id = _get_selected_id()

    # 有选择 → 尝试匹配
    if selected_id:
        browser = get_browser_by_id(selected_id)
        if browser:
            return BrowserInfo(
                **browser,
                selected=True,
            )
        # 选择的浏览器已不存在，清除选择

    # 回退：自动检测第一个兼容浏览器
    browsers = detect_all_browsers()
    for b in browsers:
        if b["compatible"]:
            return BrowserInfo(
                **b,
                selected=(not selected_id),  # 仅在无选择时标记为 selected
            )

    raise HTTPException(status_code=404, detail="未检测到任何兼容的 Chromium 内核浏览器")


@router.put(
    "/select",
    response_model=SelectBrowserResponse,
    summary="选择使用的浏览器",
    description=(
        "指定爬虫使用的浏览器，选择后持久化到数据库。"
        "传空 `browser_id` 可恢复自动检测模式。"
        "**注意**：切换浏览器后需要重启浏览器实例（或重启服务）才能生效。"
    ),
    responses={
        400: {"description": "选择的浏览器不兼容或未安装"},
    },
)
async def select_browser(req: SelectBrowserRequest) -> SelectBrowserResponse:
    browser_id = req.browser_id.strip()

    # 空字符串 → 恢复自动检测
    if not browser_id:
        settings.browser_selected_id = ""
        set_setting("browser_selected_id", "")
        return SelectBrowserResponse(
            message="已恢复为自动检测模式，下次启动浏览器时将自动选择首个可用的 Chromium 浏览器",
            browser_id="",
            restart_required=True,
        )

    # 验证浏览器存在且兼容
    browser = get_browser_by_id(browser_id)
    if not browser:
        raise HTTPException(status_code=400, detail=f"未检测到浏览器: {browser_id}")

    if not browser["compatible"]:
        raise HTTPException(
            status_code=400,
            detail=f"{browser['name']} 使用 {browser['engine']} 内核，不兼容 DrissionPage（仅支持 Chromium 内核）",
        )

    # 持久化
    settings.browser_selected_id = browser_id
    set_setting("browser_selected_id", browser_id)

    return SelectBrowserResponse(
        message=f"已选择 {browser['name']}，下次启动浏览器时生效",
        browser_id=browser_id,
        browser_name=browser["name"],
        restart_required=True,
    )
