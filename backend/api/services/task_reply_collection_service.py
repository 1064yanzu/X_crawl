"""
任务采评模式批量切换服务
"""
from __future__ import annotations

from typing import Literal

Mode = Literal["with_comments", "without_comments"]

_EDITABLE_STATUSES = {"done", "stopped", "failed"}


def _get_task_manager():
    from api.services import task_manager

    return task_manager


def _is_with_comments(task: dict) -> bool:
    platform = task.get("platform", "x")
    if platform == "weibo":
        return bool(task.get("fetch_replies"))
    return bool(task.get("fetch_replies")) and int(task.get("reply_depth", 1) or 1) >= 2


def _resolve_mode_config(mode: Mode) -> tuple[bool, int]:
    if mode == "with_comments":
        return True, 2
    return False, 1


def batch_update_reply_collection(task_ids: list[str], mode: Mode) -> dict:
    tm = _get_task_manager()
    fetch_replies, reply_depth = _resolve_mode_config(mode)

    updated_task_ids: list[str] = []
    skipped: list[dict] = []

    for task_id in task_ids:
        task = tm.get_task_summary(task_id)
        if not task:
            skipped.append({"task_id": task_id, "reason": "任务不存在"})
            continue
        if task.get("task_kind") != "search":
            skipped.append({"task_id": task_id, "reason": "仅帖子采集任务支持切换采评模式"})
            continue
        if task.get("platform", "x") not in {"x", "weibo"}:
            skipped.append({"task_id": task_id, "reason": "当前仅支持 X / 微博帖子任务切换采评模式"})
            continue
        if task.get("status") not in _EDITABLE_STATUSES:
            skipped.append({"task_id": task_id, "reason": "仅已完成/已停止/已失败任务可修改"})
            continue

        already_with_comments = _is_with_comments(task)
        if mode == "with_comments" and already_with_comments:
            skipped.append({"task_id": task_id, "reason": "该任务已开启评论采集"})
            continue
        if mode == "without_comments" and not bool(task.get("fetch_replies")):
            skipped.append({"task_id": task_id, "reason": "该任务当前已是不采集评论模式"})
            continue

        if tm.update_task_reply_collection_config(
            task_id,
            fetch_replies=fetch_replies,
            reply_depth=reply_depth,
        ):
            updated_task_ids.append(task_id)
        else:
            skipped.append({"task_id": task_id, "reason": "更新任务配置失败"})

    mode_label = "采集评论" if mode == "with_comments" else "不采集评论"
    return {
        "message": f"已切换 {len(updated_task_ids)} 个任务为「{mode_label}」模式，跳过 {len(skipped)} 个",
        "mode": mode,
        "updated_task_ids": updated_task_ids,
        "skipped": skipped,
    }
