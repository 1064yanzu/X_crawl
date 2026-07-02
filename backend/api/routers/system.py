"""
系统级运行时路由。

- GET  /api/v1/system/memory-stats        任务结果 LRU 缓存占用与命中/淘汰指标
- GET  /api/v1/system/performance-config   性能 / 磁盘清理 / WAL 配置
- PUT  /api/v1/system/performance-config   更新上述配置（持久化，重启后仍生效）
- POST /api/v1/system/diagnose             导出诊断包（日志 + schema + 脱敏配置）

与 crawler-config 解耦：此处只聚合"内存 / 磁盘 / 数据库"维度的运行时治理项，
crawler-config 仍专注抓取速率与浏览器参数。
"""
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config import settings
from api.services import task_manager
from api.services.settings_db import set_settings_batch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/system", tags=["系统"])


@router.get("/memory-stats", summary="任务结果 LRU 缓存内存统计")
async def get_memory_stats() -> dict:
    """返回任务结果 LRU 缓存占用、调度器运行态与进程 RSS（用于性能卡观测）。"""
    stats = task_manager.get_memory_stats()
    try:
        from api.services.task_scheduler import scheduler

        stats["scheduler_running"] = scheduler.running_count()
        stats["scheduler_queue"] = scheduler.queue_size()
        stats["effective_worker_limit"] = scheduler.effective_worker_limit()
    except Exception:
        pass
    try:
        import os

        import psutil

        stats["process_rss_mb"] = round(
            psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024, 1
        )
    except Exception:
        pass
    return stats


class PerformanceConfig(BaseModel):
    """内存缓存 / 磁盘归档清理 / 数据库维护配置。"""

    crawler_result_cache_max_size: int = Field(ge=4, le=64, description="任务结果 LRU 条目上限")
    crawler_result_cache_max_mb: float = Field(ge=64, le=4096, description="任务结果 LRU 内存上限（MB）")
    raw_responses_cleanup_enabled: bool = Field(description="是否启用 raw_responses 滚动清理")
    raw_responses_cleanup_interval_min: int = Field(ge=5, le=1440, description="滚动清理执行间隔（分钟）")
    raw_responses_terminal_ttl_hours: float = Field(ge=1, le=720, description="终态任务归档保留时长（小时）")
    raw_responses_task_max_mb: float = Field(ge=16, le=10240, description="单任务归档大小上限（MB）")
    raw_responses_global_max_gb: float = Field(ge=0.5, le=200, description="全局归档大小上限（GB）")
    db_wal_checkpoint_interval_min: int = Field(ge=0, le=1440, description="WAL checkpoint 周期（分钟，0=禁用）")


_PERF_KEYS = tuple(PerformanceConfig.model_fields.keys())


def _current_performance_config() -> PerformanceConfig:
    return PerformanceConfig(
        crawler_result_cache_max_size=int(getattr(settings, "crawler_result_cache_max_size", 16)),
        crawler_result_cache_max_mb=float(getattr(settings, "crawler_result_cache_max_mb", 512.0)),
        raw_responses_cleanup_enabled=bool(getattr(settings, "raw_responses_cleanup_enabled", True)),
        raw_responses_cleanup_interval_min=int(getattr(settings, "raw_responses_cleanup_interval_min", 30)),
        raw_responses_terminal_ttl_hours=float(getattr(settings, "raw_responses_terminal_ttl_hours", 24.0)),
        raw_responses_task_max_mb=float(getattr(settings, "raw_responses_task_max_mb", 512.0)),
        raw_responses_global_max_gb=float(getattr(settings, "raw_responses_global_max_gb", 2.0)),
        db_wal_checkpoint_interval_min=int(getattr(settings, "db_wal_checkpoint_interval_min", 10)),
    )


@router.get("/performance-config", response_model=PerformanceConfig, summary="获取性能/清理配置")
async def get_performance_config() -> PerformanceConfig:
    return _current_performance_config()


@router.put("/performance-config", response_model=PerformanceConfig, summary="更新性能/清理配置")
async def update_performance_config(config: PerformanceConfig) -> PerformanceConfig:
    """更新性能/清理配置，立即生效并持久化。"""
    payload = config.model_dump()
    for key, value in payload.items():
        setattr(settings, key, value)
    set_settings_batch(payload)

    # 通知后台清理守护刷新间隔（存在才调用）
    try:
        from crawler.response_saver import reschedule_cleanup

        reschedule_cleanup()
    except Exception:
        pass
    return _current_performance_config()


@router.get("/about", summary="桌面端 About 信息（版本 + 迁移历史 + 路径）")
async def get_about() -> dict:
    """供 AboutCard 一次性聚合：版本、构建期、SHA256（如存在）、迁移历史、关键路径。"""
    import os
    import platform
    import sys
    from pathlib import Path

    from config import settings as cfg

    about = {
        "version": "1.1.1",
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "data_dir": cfg.data_dir,
        "tasks_db": str(Path(cfg.data_dir) / cfg.tasks_db_path),
        "raw_responses_dir": str(Path(cfg.data_dir) / cfg.raw_responses_dir),
        "log_dir": str(cfg.log_dir or Path(cfg.data_dir) / "logs"),
        "dev_mode": os.environ.get("XCRAWL_DEV_MODE", "") == "1",
    }
    # 迁移历史
    try:
        from api.services import task_db
        from api.services.migrations import get_migration_history

        about["migrations"] = get_migration_history(task_db._get_conn())
    except Exception as e:
        about["migrations"] = {"error": str(e)}
    return about


@router.post("/diagnose", summary="导出诊断包（日志 + schema + 脱敏配置）")
async def export_diagnose() -> dict:
    """
    打包诊断信息到 zip 文件，返回文件路径。文件落在数据目录，前端通过桌面 IPC 打开数据目录。

    包含：
      - logs/*.log（最近 N 个）
      - tasks.db 的 schema（不含数据）
      - settings 快照（cookie 字段脱敏）
      - 系统信息
    """
    import json
    import time
    import zipfile
    from pathlib import Path

    from config import settings as cfg

    data_root = Path(cfg.data_dir)
    log_dir = Path(cfg.log_dir) if cfg.log_dir else data_root / "logs"
    ts = time.strftime("%Y%m%dT%H%M%S")
    out_path = data_root / f"xcrawl-diagnose-{ts}.zip"

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 日志（最近 5 个，去重避免 zip 内同名冲突）
        if log_dir.exists():
            log_files = sorted(log_dir.rglob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
            seen_names: set[str] = set()
            for f in log_files:
                arc = f.name
                if arc in seen_names:
                    arc = f"{f.parent.name}__{f.name}"
                seen_names.add(arc)
                try:
                    zf.write(f, arcname=f"logs/{arc}")
                except Exception:
                    pass

        # schema（不含数据）
        try:
            from api.services import task_db

            conn = task_db._get_conn()
            schema_lines = []
            for row in conn.execute(
                "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ):
                if row["sql"]:
                    schema_lines.append(f"-- {row['type']}: {row['name']}\n{row['sql']};\n")
            zf.writestr("schema.sql", "\n".join(schema_lines))
        except Exception as e:
            zf.writestr("schema-error.txt", str(e))

        # 脱敏的配置快照
        try:
            redacted = {}
            for k, v in cfg.model_dump().items():
                kl = k.lower()
                if any(s in kl for s in ("cookie", "secret", "token", "api_key", "proxy")):
                    redacted[k] = "<redacted>"
                else:
                    redacted[k] = v
            zf.writestr("settings.json", json.dumps(redacted, ensure_ascii=False, indent=2))
        except Exception as e:
            zf.writestr("settings-error.txt", str(e))

        # 系统信息
        import platform
        import sys

        zf.writestr(
            "system.txt",
            "\n".join([
                f"python={sys.version}",
                f"platform={platform.platform()}",
                f"machine={platform.machine()}",
                f"ts={ts}",
            ]),
        )

    return {
        "path": str(out_path),
        "size_bytes": out_path.stat().st_size,
        "filename": out_path.name,
    }
