"""
Schema 版本化迁移注册中心。

设计：
- SQLite 的 `PRAGMA user_version` 作为单调递增的当前版本号
- `MIGRATIONS` 列表声明从 0 → 1 → 2 → ... 的迁移函数
- 每次启动 init_db 后调用 apply_pending(conn)，按顺序执行未应用的迁移
- 迁移前自动备份 tasks.db → tasks.db.before-migrate-<ts>

不依赖 alembic：当前 schema 由 `_ensure_column` 已实现增量补列；本框架
用于后续真正破坏性的 schema 变更（重命名 / 拆表 / 索引重建）。
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# (target_version, description, function) — function 接收 conn，函数内自行提交
MIGRATIONS: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    # 示例占位：(1, "初始基线", lambda c: None),
]


def get_current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def _backup_db(db_path: Path) -> Path | None:
    """迁移前自动备份。返回备份文件路径；失败返回 None。"""
    if not db_path.exists():
        return None
    ts = time.strftime("%Y%m%dT%H%M%S")
    backup = db_path.with_name(f"{db_path.name}.before-migrate-{ts}.db")
    try:
        shutil.copy2(db_path, backup)
        logger.info(f"已备份数据库到 {backup.name}")
        return backup
    except Exception as e:
        logger.warning(f"备份数据库失败（继续迁移）: {e}")
        return None


def apply_pending(conn: sqlite3.Connection, db_path: Path) -> dict:
    """检查并应用挂起的迁移。

    Returns: {"from": current_version, "to": new_version, "applied": [..], "backup": str|None}
    """
    current = get_current_version(conn)
    target_migrations = [m for m in MIGRATIONS if m[0] > current]
    if not target_migrations:
        return {"from": current, "to": current, "applied": [], "backup": None}

    backup = _backup_db(db_path)
    applied: list[int] = []
    try:
        for version, desc, fn in sorted(target_migrations):
            logger.info(f"应用迁移 v{version}: {desc}")
            fn(conn)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
            applied.append(version)
        new_version = get_current_version(conn)
        return {
            "from": current,
            "to": new_version,
            "applied": applied,
            "backup": str(backup) if backup else None,
        }
    except Exception as e:
        logger.error(f"迁移失败 applied={applied} error={e}", exc_info=True)
        raise


def get_migration_history(conn: sqlite3.Connection) -> dict:
    """暴露给前端 AboutCard 展示。"""
    return {
        "current_version": get_current_version(conn),
        "latest_version": max((m[0] for m in MIGRATIONS), default=0),
        "registered": [
            {"version": v, "description": d} for v, d, _ in sorted(MIGRATIONS)
        ],
    }
