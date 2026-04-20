"""
YouTube 视频 URL / ID 解析工具。

给定用户粘贴的任意文本或字符串列表，提取出有效的 11 位 video ID：
- https://youtu.be/<id>[?...]
- https://www.youtube.com/watch?v=<id>[&...]
- https://m.youtube.com/watch?v=<id>[&...]
- https://music.youtube.com/watch?v=<id>[&...]
- https://www.youtube.com/shorts/<id>
- https://www.youtube.com/embed/<id>
- https://www.youtube.com/v/<id>
- 纯 11 位 video ID

规则：
- 按换行 / 逗号 / 分号 / 空白拆分原始输入
- 每一段都过一遍匹配；匹配失败原样保留到 invalid 列表
- 最终返回 (valid_ids_unique_ordered, invalid_lines)
- 去重保留首次出现顺序，便于用户对比输入

前端应有一份等价的 TS 实现（frontend/src/lib/youtube-url.ts），规则保持同步。
"""
from __future__ import annotations

import re
from typing import Iterable, Union

# YouTube video ID 是严格 11 位 [A-Za-z0-9_-]
_VIDEO_ID_CHARSET = r"[0-9A-Za-z_\-]{11}"
_VIDEO_ID_STRICT_RE = re.compile(rf"^{_VIDEO_ID_CHARSET}$")

# URL 解析模式（按优先级匹配，谁先命中 11 位就用谁）
_URL_PATTERNS = [
    re.compile(rf"youtu\.be/({_VIDEO_ID_CHARSET})(?:[/?&#]|$)"),
    re.compile(rf"youtube\.com/shorts/({_VIDEO_ID_CHARSET})(?:[/?&#]|$)"),
    re.compile(rf"youtube\.com/embed/({_VIDEO_ID_CHARSET})(?:[/?&#]|$)"),
    re.compile(rf"youtube\.com/v/({_VIDEO_ID_CHARSET})(?:[/?&#]|$)"),
    re.compile(rf"youtube\.com/watch\?(?:[^#]*&)?v=({_VIDEO_ID_CHARSET})(?:[&#]|$)"),
]

_SPLIT_RE = re.compile(r"[\s,;]+")


def _extract_one(chunk: str) -> str:
    """从单段文本中提取出一个 video ID；找不到返回空串。"""
    text = (chunk or "").strip()
    if not text:
        return ""
    # 直接是 11 位 ID
    if _VIDEO_ID_STRICT_RE.match(text):
        return text
    for pattern in _URL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return ""


def parse_video_ids(raw: Union[str, Iterable[str], None]) -> tuple[list[str], list[str]]:
    """
    把用户输入（单个字符串或字符串列表）解析为 YouTube video ID 列表。

    :return: (去重后的有效 id 列表, 无法解析的原始段)
    """
    if raw is None:
        return [], []

    chunks: list[str] = []
    if isinstance(raw, str):
        chunks.extend(part for part in _SPLIT_RE.split(raw) if part.strip())
    else:
        for item in raw:
            if not isinstance(item, str):
                continue
            chunks.extend(part for part in _SPLIT_RE.split(item) if part.strip())

    seen: set[str] = set()
    valid: list[str] = []
    invalid: list[str] = []
    for chunk in chunks:
        vid = _extract_one(chunk)
        if vid:
            if vid not in seen:
                seen.add(vid)
                valid.append(vid)
        else:
            invalid.append(chunk.strip())
    return valid, invalid


def is_valid_video_id(value: str) -> bool:
    """标准 11 位 YouTube video ID 校验。"""
    return bool(value) and bool(_VIDEO_ID_STRICT_RE.match(value))
