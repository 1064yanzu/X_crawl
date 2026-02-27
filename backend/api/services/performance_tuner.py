"""
启动性能调优器。

目标：
- 仅在发现“明显过慢”配置时做安全收敛
- 不改爬虫特征面（UA/指纹/请求头不变）
- 调优结果持久化，避免每次启动重复偏慢
"""
from __future__ import annotations

import logging

from config import settings

logger = logging.getLogger(__name__)

_SAFE_CEILINGS: dict[str, float] = {
    "crawler_initial_wait": 3.0,
    "crawler_reply_wait": 4.0,
    "crawler_page_interval": 4.0,
    "crawler_page_interval_min": 2.0,
    "crawler_page_interval_max": 6.0,
}


def _cap_if_too_slow(key: str, ceiling: float, changed: dict[str, float]) -> None:
    current = float(getattr(settings, key))
    if current <= ceiling:
        return
    setattr(settings, key, ceiling)
    changed[key] = ceiling


def apply_startup_performance_tuning() -> dict[str, float]:
    """
    对过慢配置做一次启动自动调优并持久化。

    Returns:
        被自动收敛的配置项（空字典表示无需调整）
    """
    changed: dict[str, float] = {}

    for key, ceiling in _SAFE_CEILINGS.items():
        _cap_if_too_slow(key, ceiling, changed)

    # 约束区间关系
    min_wait = float(settings.crawler_page_interval_min)
    max_wait = float(settings.crawler_page_interval_max)
    if min_wait > max_wait:
        min_wait = max(0.5, min_wait)
        max_wait = min_wait
        settings.crawler_page_interval_min = min_wait
        settings.crawler_page_interval_max = max_wait
        changed["crawler_page_interval_min"] = min_wait
        changed["crawler_page_interval_max"] = max_wait

    # 基线翻页间隔应落在 min/max 区间
    page_interval = float(settings.crawler_page_interval)
    if page_interval < min_wait:
        settings.crawler_page_interval = min_wait
        changed["crawler_page_interval"] = min_wait
    elif page_interval > max_wait:
        settings.crawler_page_interval = max_wait
        changed["crawler_page_interval"] = max_wait

    if not changed:
        return {}

    try:
        from api.services.settings_db import set_settings_batch

        set_settings_batch(changed)
        logger.info(
            "已应用启动性能自动调优并持久化: %s",
            ", ".join(f"{k}={v}" for k, v in changed.items()),
        )
    except Exception as e:
        logger.warning("性能调优持久化失败（仅内存生效）: %s", e)

    return changed

