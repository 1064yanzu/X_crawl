"""
YouTube Data API v3 HTTP 客户端。

职责：
- 封装 requests session，gzip + 超时
- 每次调用自动从 Key 池取 key、扣配额、记录使用
- 403 quotaExceeded → 标记 Key exhausted 并切换下一个
- 400 keyInvalid / API key not valid → 标记 Key invalid
- 429 / 5xx → 有限次重试（保留上游错误信息）
- 所有上层调用都应通过本文件的 call_list() 入口
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Optional

import requests

from . import api_key_pool, quota_tracker

logger = logging.getLogger(__name__)

BASE_URL = "https://www.googleapis.com/youtube/v3"
DEFAULT_TIMEOUT = 20.0
MAX_ATTEMPTS = 5  # 最多尝试次数（覆盖重试 + 切 Key）
RETRY_STATUS = {500, 502, 503, 504}


class YouTubeApiError(RuntimeError):
    """YouTube API 调用失败（经过重试后仍无法恢复）。"""

    def __init__(self, message: str, *, status: Optional[int] = None, reason: Optional[str] = None) -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason


class YouTubeQuotaExhausted(YouTubeApiError):
    """所有 Key 配额耗尽；上层应将任务切到 paused(rate_limited)。"""

    def __init__(self, message: str, *, reset_at: Optional[str] = None) -> None:
        super().__init__(message, status=403, reason="quotaExceeded")
        self.reset_at = reset_at


class YouTubeKeyMissing(YouTubeApiError):
    """未配置任何 API Key。"""

    def __init__(self, message: str = "未配置任何启用状态的 YouTube API Key") -> None:
        super().__init__(message, status=0, reason="key_missing")


_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        sess = requests.Session()
        sess.headers.update(
            {
                "Accept-Encoding": "gzip",
                "User-Agent": "x-crawl-youtube/1.0 (gzip)",
                "Accept": "application/json",
            }
        )
        _session = sess
    return _session


def call_list(
    endpoint: str,
    params: dict,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    extra_cost: int = 0,
    task_id: Optional[str] = None,
    archive_context: Optional[str] = None,
    archive_page: Optional[int] = None,
) -> dict:
    """
    调用 YouTube list 类端点，返回解析后的 JSON。

    :param endpoint: 点号风格，如 "videos.list" / "commentThreads.list"
    :param params: 查询参数（不含 key）
    :param extra_cost: 若该端点有多 part 组合等特殊成本，可附加单位
    :param task_id: 若提供，本次响应会落盘到 raw_responses/{task_id}/youtube/...
    :param archive_context: 存档路径中的二级分组（如 "video_{vid}"、"video_{vid}/parent_{pid}"）
    :param archive_page: 可选的页码，写进文件名方便排序
    :raises YouTubeApiError / YouTubeQuotaExhausted / YouTubeKeyMissing
    """
    pool = api_key_pool.get_pool()
    path = endpoint.split(".")[0]
    url = f"{BASE_URL}/{path}"
    cost = quota_tracker.cost_of(endpoint) + int(extra_cost or 0)

    tried_keys: set[str] = set()
    last_error: Optional[str] = None
    last_status: Optional[int] = None
    last_reason: Optional[str] = None
    last_reset_at: Optional[str] = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            key = pool.pick_available(cost)
        except api_key_pool.KeyPoolExhausted as exc:
            raise YouTubeQuotaExhausted(str(exc), reset_at=exc.reset_at) from exc
        except api_key_pool.NoKeyAvailable as exc:
            raise YouTubeKeyMissing(str(exc)) from exc

        if key.key_id in tried_keys and len(tried_keys) >= _active_key_count(pool):
            # 所有 Key 都被尝试过且失败，不再循环
            break
        tried_keys.add(key.key_id)

        query = dict(params)
        query["key"] = key.api_key
        try:
            session = _get_session()
            resp = session.get(url, params=query, timeout=timeout)
        except requests.RequestException as exc:
            last_error = f"网络请求失败: {exc}"
            last_status = None
            last_reason = "network_error"
            pool.record_failure(key.key_id, reason=str(exc))
            _backoff(attempt)
            continue

        status = resp.status_code
        if status == 200:
            try:
                payload = resp.json()
            except ValueError as exc:
                last_error = f"响应 JSON 解析失败: {exc}"
                last_status = status
                last_reason = "invalid_json"
                pool.record_failure(key.key_id, reason="invalid_json")
                _backoff(attempt)
                continue
            pool.record_usage(key.key_id, cost=cost)
            # 所有任务都落盘原始响应——即使任务之后被中断/挂掉/重启，
            # 仍能从 raw_responses 完整重建 tweets 与 replies。
            if task_id:
                try:
                    from crawler.response_saver import save_youtube_response
                    save_youtube_response(
                        task_id,
                        endpoint,
                        payload,
                        context=archive_context,
                        page_num=archive_page,
                    )
                except Exception as exc:
                    logger.debug(
                        "保存 YouTube 原始响应失败（忽略，不影响主流程）task=%s endpoint=%s: %s",
                        task_id, endpoint, exc,
                    )
            return payload

        # 非 200：解析错误原因
        err_payload = _extract_error(resp)
        reason = err_payload.get("reason") or ""
        message = err_payload.get("message") or resp.text[:240]
        last_status = status
        last_reason = reason
        last_error = f"HTTP {status} {reason}: {message}"

        logger.warning(
            "YouTube API 调用失败 endpoint=%s status=%s reason=%s key=%s",
            endpoint,
            status,
            reason,
            key.alias,
        )

        if status == 403:
            if reason in ("quotaExceeded", "dailyLimitExceeded", "userRateLimitExceeded"):
                reset_at = quota_tracker.compute_next_pt_midnight().isoformat()
                pool.mark_exhausted(key.key_id, reset_at=reset_at)
                last_reset_at = reset_at
                continue  # 换一个 Key 继续
            if reason in ("keyInvalid", "forbidden", "ipRefererBlocked", "commentsDisabled"):
                if reason == "commentsDisabled":
                    # 视频层级问题，不属于 Key 错误；直接向上抛
                    raise YouTubeApiError(last_error, status=status, reason=reason)
                pool.mark_invalid(key.key_id, reason=reason)
                continue
            # 其它 403 归类为 Key 可用性问题，记作失败并换 Key
            pool.record_failure(key.key_id, reason=reason or "forbidden")
            continue

        if status == 400 and reason == "keyInvalid":
            pool.mark_invalid(key.key_id, reason=reason)
            continue

        if status == 429:
            pool.record_failure(key.key_id, reason="rate_limited")
            _backoff(attempt, base=2.5)
            continue

        if status in RETRY_STATUS:
            pool.record_failure(key.key_id, reason=f"http_{status}")
            _backoff(attempt)
            continue

        # 其它错误直接终止（一般是 400 参数错误）
        raise YouTubeApiError(last_error, status=status, reason=reason)

    # 所有尝试都失败
    if last_reason in ("quotaExceeded", "dailyLimitExceeded"):
        raise YouTubeQuotaExhausted(
            last_error or "YouTube 配额耗尽",
            reset_at=last_reset_at,
        )
    raise YouTubeApiError(
        last_error or "YouTube API 调用失败",
        status=last_status,
        reason=last_reason,
    )


def validate_key(api_key: str, *, timeout: float = 8.0) -> dict:
    """
    用一次极轻量调用验证 Key 是否可用。
    调用 i18nRegions.list（1 单位），返回 { ok, message, status, reason }。
    """
    url = f"{BASE_URL}/i18nRegions"
    params = {"part": "snippet", "hl": "en_US", "key": api_key}
    try:
        resp = _get_session().get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        return {"ok": False, "message": f"网络异常: {exc}", "status": 0, "reason": "network_error"}

    if resp.status_code == 200:
        return {"ok": True, "message": "Key 验证通过", "status": 200, "reason": None}

    err = _extract_error(resp)
    return {
        "ok": False,
        "message": err.get("message") or resp.text[:240],
        "status": resp.status_code,
        "reason": err.get("reason") or "",
    }


def _extract_error(resp: requests.Response) -> dict:
    try:
        data = resp.json() or {}
    except ValueError:
        return {}
    error = data.get("error") or {}
    errors_list = error.get("errors") or []
    reason = errors_list[0].get("reason") if errors_list else error.get("status")
    message = error.get("message") or ""
    return {"reason": reason, "message": message}


def _active_key_count(pool: api_key_pool.YouTubeApiKeyPool) -> int:
    return sum(
        1
        for k in pool.list_keys()
        if k.enabled and k.status != "invalid"
    )


def _backoff(attempt: int, *, base: float = 1.2) -> None:
    delay = min(6.0, base * (attempt + 1)) + random.uniform(0.1, 0.4)
    time.sleep(delay)


def iter_pages(
    endpoint: str,
    params: dict,
    *,
    max_pages: Optional[int] = None,
    extra_cost: int = 0,
    timeout: float = DEFAULT_TIMEOUT,
):
    """
    以生成器方式分页调用 list 端点。
    每一页是一次独立 cost，上层需要处理 `check_signal`/暂停语义。
    """
    next_token: Optional[str] = params.get("pageToken")
    page_index = 0
    while True:
        query = dict(params)
        if next_token:
            query["pageToken"] = next_token
        elif "pageToken" in query:
            query.pop("pageToken", None)

        payload = call_list(endpoint, query, extra_cost=extra_cost, timeout=timeout)
        yield page_index, payload

        next_token = payload.get("nextPageToken")
        page_index += 1
        if not next_token:
            break
        if max_pages is not None and page_index >= max_pages:
            break
