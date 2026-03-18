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
):
    """等待目标 JSON 包，忽略无关包，直到超时。"""
    deadline = time.monotonic() + max(0.5, timeout)
    ignored = 0

    while time.monotonic() < deadline:
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


def is_tweet_detail_body(body: dict) -> bool:
    try:
        return "threaded_conversation_with_injections_v2" in body["data"]
    except Exception:
        return False
