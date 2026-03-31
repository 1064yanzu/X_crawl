"""监听数据包守卫：过滤无关数据包并保证响应结构可解析。"""
from __future__ import annotations

import json
import time
from typing import Callable, Optional, Any


BodyPredicate = Callable[[dict], bool]
PacketObserver = Callable[[Any, Optional[dict]], None]


def extract_packet_body_dict(packet) -> Optional[dict]:
    try:
        body = packet.response.body
        if isinstance(body, dict):
            return body
        if isinstance(body, str):
            text = body.strip()
            if text.startswith("{") or text.startswith("["):
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
    except Exception:
        return None
    return None


def wait_for_target_packet(
    tab,
    *,
    timeout: float,
    accept_body: BodyPredicate,
    max_ignored: int = 30,
    on_packet: PacketObserver | None = None,
    early_exit_check: "Callable[[], bool] | None" = None,
):
    """等待目标 JSON 包，忽略无关包，直到超时。
    
    Args:
        early_exit_check: 可选回调，在每次等待循环时调用；
                          若返回 True，则立即退出等待（用于检测页面无结果等情况）
    """
    deadline = time.monotonic() + max(0.5, timeout)
    ignored = 0

    while time.monotonic() < deadline:
        # 早期退出检查（如检测到页面显示"无结果"）
        if early_exit_check is not None and early_exit_check():
            return None, ignored
        
        remaining = max(0.2, deadline - time.monotonic())
        try:
            packet = tab.listen.wait(timeout=min(remaining, 1.5), raise_err=False)
        except (UnboundLocalError, RuntimeError):
            # DrissionPage bug: 浏览器停止时 fail 变量未赋值；RuntimeError 表示监听已停止
            return None, ignored
        if not packet:
            continue

        body = extract_packet_body_dict(packet)
        if on_packet is not None:
            on_packet(packet, body)
        if body is None:
            ignored += 1
            if ignored >= max_ignored:
                break
            continue

        if accept_body(body):
            return packet, ignored

        ignored += 1
        if ignored >= max_ignored:
            break

    return None, ignored


def is_search_timeline_body(body: dict) -> bool:
    try:
        return "search_timeline" in body["data"]["search_by_raw_query"]
    except Exception:
        return False


def _iter_timeline_entries(body: dict):
    try:
        instructions = (
            body["data"]["search_by_raw_query"]["search_timeline"]["timeline"]["instructions"]
        )
    except Exception:
        return

    if not isinstance(instructions, list):
        return

    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        entries = instruction.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    yield entry
        entry = instruction.get("entry")
        if isinstance(entry, dict):
            yield entry


def _module_has_tweet_item(content: dict) -> bool:
    items = content.get("items")
    if not isinstance(items, list):
        return False

    for item in items:
        if not isinstance(item, dict):
            continue
        item_node = item.get("item", {}) if isinstance(item.get("item"), dict) else {}
        item_content = item_node.get("itemContent") or item.get("itemContent") or {}
        if isinstance(item_content, dict) and item_content.get("__typename") == "TimelineTweet":
            return True
    return False


def has_search_results_entries(body: dict) -> bool:
    """判断 SearchTimeline 响应中是否真的携带了推文实体，而不只是 cursor 更新包。"""
    for entry in _iter_timeline_entries(body) or ():
        content = entry.get("content", {})
        if not isinstance(content, dict):
            continue
        typename = content.get("__typename")
        if typename == "TimelineTimelineItem":
            item_content = content.get("itemContent", {})
            if isinstance(item_content, dict) and item_content.get("__typename") == "TimelineTweet":
                return True
        if typename == "TimelineTimelineModule" and _module_has_tweet_item(content):
            return True
    return False


def is_contentful_search_timeline_body(body: dict) -> bool:
    return is_search_timeline_body(body) and has_search_results_entries(body)


def is_tweet_detail_body(body: dict) -> bool:
    try:
        return "threaded_conversation_with_injections_v2" in body["data"]
    except Exception:
        return False
