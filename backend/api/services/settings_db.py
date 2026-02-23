"""
用户设置持久化层

key-value 结构存储用户在设置界面配置的所有参数。
用户设置优先级高于 .env 环境变量。

表结构：
- key:        设置项键名（如 crawler_timeout, browser_headless）
- value:      JSON 序列化的值
- updated_at: 最后更新时间
"""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_conn():
    """复用 task_db 的数据库连接"""
    from api.services.task_db import _get_conn as _db_conn
    return _db_conn()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_setting(key: str):
    """获取单个设置项的值，不存在返回 None"""
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM user_settings WHERE key = ?", (key,)
            ).fetchone()
        if row:
            return json.loads(row["value"])
        return None
    except Exception as e:
        logger.error(f"读取设置失败: key={key}: {e}", exc_info=True)
        return None


def set_setting(key: str, value) -> None:
    """写入/更新设置项"""
    try:
        json_val = json.dumps(value, ensure_ascii=False)
        with _get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_settings (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, json_val, _now_iso()))
            conn.commit()
    except Exception as e:
        logger.error(f"写入设置失败: key={key}: {e}", exc_info=True)


def set_settings_batch(settings: dict) -> None:
    """批量写入设置项"""
    try:
        now = _now_iso()
        with _get_conn() as conn:
            for key, value in settings.items():
                json_val = json.dumps(value, ensure_ascii=False)
                conn.execute("""
                    INSERT OR REPLACE INTO user_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                """, (key, json_val, now))
            conn.commit()
    except Exception as e:
        logger.error(f"批量写入设置失败: {e}", exc_info=True)


def get_all_settings() -> dict:
    """获取所有设置项，返回 {key: parsed_value} 字典"""
    try:
        with _get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM user_settings").fetchall()
        result = {}
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                result[row["key"]] = row["value"]
        return result
    except Exception as e:
        logger.error(f"读取全部设置失败: {e}", exc_info=True)
        return {}


def delete_setting(key: str) -> bool:
    """删除单个设置项"""
    try:
        with _get_conn() as conn:
            cursor = conn.execute("DELETE FROM user_settings WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"删除设置失败: key={key}: {e}", exc_info=True)
        return False
