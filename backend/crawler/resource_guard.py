"""系统资源采样与爬取节流策略。"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from config import settings

try:  # pragma: no cover - 依赖存在时走 psutil
    import psutil  # type: ignore
except Exception:  # pragma: no cover - 无 psutil 走降级
    psutil = None


@dataclass(slots=True)
class ResourceSample:
    sampled_mono: float
    host_mem_used_percent: float
    host_mem_available_mb: float
    host_cpu_percent: float
    process_rss_mb: float
    process_cpu_percent: float


_lock = threading.RLock()
_cached_sample: ResourceSample | None = None
_process = psutil.Process(os.getpid()) if psutil else None

if _process is not None:  # 预热 CPU 采样，避免首次 always 0
    try:
        _process.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None)
    except Exception:
        pass


def _sample_interval_sec() -> float:
    return max(0.5, float(getattr(settings, "crawler_resource_sample_interval_sec", 2.0)))


def _sample_with_psutil(now_mono: float) -> ResourceSample:
    vm = psutil.virtual_memory()
    host_mem_used = float(vm.percent)
    host_mem_available_mb = float(vm.available) / 1024.0 / 1024.0

    host_cpu = float(psutil.cpu_percent(interval=None))

    proc_rss_mb = 0.0
    proc_cpu = 0.0
    if _process is not None:
        try:
            proc_rss_mb = float(_process.memory_info().rss) / 1024.0 / 1024.0
            proc_cpu = float(_process.cpu_percent(interval=None))
        except Exception:
            pass

    return ResourceSample(
        sampled_mono=now_mono,
        host_mem_used_percent=round(host_mem_used, 2),
        host_mem_available_mb=round(host_mem_available_mb, 2),
        host_cpu_percent=round(host_cpu, 2),
        process_rss_mb=round(proc_rss_mb, 2),
        process_cpu_percent=round(proc_cpu, 2),
    )


def _sample_fallback(now_mono: float) -> ResourceSample:
    # 无 psutil 时提供最小可用信息，避免影响主流程
    return ResourceSample(
        sampled_mono=now_mono,
        host_mem_used_percent=0.0,
        host_mem_available_mb=0.0,
        host_cpu_percent=0.0,
        process_rss_mb=0.0,
        process_cpu_percent=0.0,
    )


def get_resource_sample(*, force: bool = False) -> ResourceSample:
    global _cached_sample
    now_mono = time.monotonic()

    with _lock:
        if (
            not force
            and _cached_sample is not None
            and (now_mono - _cached_sample.sampled_mono) < _sample_interval_sec()
        ):
            return _cached_sample

        if psutil is not None:
            sample = _sample_with_psutil(now_mono)
        else:
            sample = _sample_fallback(now_mono)
        _cached_sample = sample
        return sample


def _pressure_state(sample: ResourceSample) -> str:
    mem_warn = float(getattr(settings, "crawler_memory_pressure_warn_pct", 80.0))
    mem_critical = max(mem_warn + 1.0, float(getattr(settings, "crawler_memory_pressure_critical_pct", 90.0)))
    cpu_warn = float(getattr(settings, "crawler_cpu_pressure_warn_pct", 85.0))
    cpu_critical = max(cpu_warn + 1.0, float(getattr(settings, "crawler_cpu_pressure_critical_pct", 95.0)))

    mem = sample.host_mem_used_percent
    cpu = sample.host_cpu_percent

    if mem >= mem_critical or cpu >= cpu_critical:
        return "critical"
    if mem >= mem_warn or cpu >= cpu_warn:
        return "warning"
    return "normal"


def get_throttle_multiplier() -> tuple[float, str]:
    """返回当前节流因子与压力状态。"""
    if not bool(getattr(settings, "crawler_auto_throttle_enabled", True)):
        return 1.0, "normal"

    sample = get_resource_sample()
    state = _pressure_state(sample)
    max_factor = max(1.2, float(getattr(settings, "crawler_resource_throttle_max_factor", 3.0)))

    if state == "normal":
        return 1.0, state

    mem_warn = float(getattr(settings, "crawler_memory_pressure_warn_pct", 80.0))
    mem_critical = max(mem_warn + 1.0, float(getattr(settings, "crawler_memory_pressure_critical_pct", 90.0)))

    mem = sample.host_mem_used_percent

    if state == "warning":
        ratio = min(1.0, max(0.0, (mem - mem_warn) / max(1.0, mem_critical - mem_warn)))
        factor = 1.25 + ratio * 0.65
    else:
        factor = 2.0 + max(0.0, (mem - mem_critical)) * 0.05

    factor = min(max_factor, max(1.0, factor))
    return round(factor, 2), state


def effective_worker_limit(configured: int) -> int:
    workers = max(1, int(configured))
    if workers <= 1:
        return 1
    if not bool(getattr(settings, "crawler_dynamic_concurrency_enabled", True)):
        return workers

    _, state = get_throttle_multiplier()
    if state == "critical":
        return 1
    if state == "warning":
        return max(1, workers - 1)
    return workers


def get_resource_metrics() -> dict:
    sample = get_resource_sample()
    factor, state = get_throttle_multiplier()
    age_sec = max(0.0, time.monotonic() - sample.sampled_mono)
    return {
        "host_mem_used_percent": sample.host_mem_used_percent,
        "host_mem_available_mb": sample.host_mem_available_mb,
        "host_cpu_percent": sample.host_cpu_percent,
        "process_rss_mb": sample.process_rss_mb,
        "process_cpu_percent": sample.process_cpu_percent,
        "resource_pressure_state": state,
        "crawl_throttle_factor": factor,
        "resource_sample_age_sec": round(age_sec, 2),
    }
