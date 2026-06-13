#!/usr/bin/env python3
"""
SQLite 数据库 VACUUM 工具

用于回收已删除数据占用的磁盘空间。
建议在服务停止时运行，避免锁冲突。

使用方法：
    python vacuum_database.py
"""
import sqlite3
import sys
from pathlib import Path

# 假设脚本在 backend/ 目录下运行
DB_PATH = Path(__file__).parent / "tasks.db"


def get_db_size(path: Path) -> int:
    """获取数据库文件大小（字节）"""
    if not path.exists():
        return 0
    return path.stat().st_size


def format_size(bytes_size: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} TB"


def main():
    if not DB_PATH.exists():
        print(f"❌ 数据库文件不存在: {DB_PATH}")
        sys.exit(1)

    print(f"📊 数据库路径: {DB_PATH}")

    # 获取原始大小
    original_size = get_db_size(DB_PATH)
    print(f"📦 原始大小: {format_size(original_size)}")

    # 检查 WAL 和 SHM 文件
    wal_path = DB_PATH.with_suffix(".db-wal")
    shm_path = DB_PATH.with_suffix(".db-shm")

    if wal_path.exists():
        wal_size = get_db_size(wal_path)
        print(f"📄 WAL 文件: {format_size(wal_size)}")

    if shm_path.exists():
        shm_size = get_db_size(shm_path)
        print(f"📄 SHM 文件: {format_size(shm_size)}")

    print("\n⚠️  警告：请确保后端服务已停止，否则可能导致锁冲突！")
    print("⚠️  VACUUM 操作可能需要几分钟，请耐心等待...\n")

    response = input("是否继续执行 VACUUM？(yes/no): ")
    if response.lower() not in ("yes", "y"):
        print("❌ 操作已取消")
        sys.exit(0)

    try:
        print("\n🔧 正在执行 VACUUM...")
        conn = sqlite3.connect(str(DB_PATH))

        # 设置超时（30 秒）
        conn.execute("PRAGMA busy_timeout = 30000")

        # 执行 VACUUM
        conn.execute("VACUUM")

        # 优化数据库
        conn.execute("PRAGMA optimize")

        conn.close()
        print("✅ VACUUM 完成")

        # 获取优化后的大小
        new_size = get_db_size(DB_PATH)
        saved_size = original_size - new_size
        saved_percent = (saved_size / original_size * 100) if original_size > 0 else 0

        print(f"\n📊 优化后大小: {format_size(new_size)}")
        print(f"💾 释放空间: {format_size(saved_size)} ({saved_percent:.1f}%)")

        if saved_size > 0:
            print("✨ 优化成功！")
        else:
            print("ℹ️  数据库已经很紧凑，无需进一步优化")

    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            print("\n❌ 错误：数据库被锁定")
            print("   请确保后端服务已完全停止，然后重试")
        else:
            print(f"\n❌ 错误：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 未知错误：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
