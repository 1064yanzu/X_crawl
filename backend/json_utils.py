from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any


def normalize_json_value(value: Any) -> Any:
    """递归归一化为 JSON 兼容结构，优先保留对象自定义的 to_dict 结果。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, dict):
        return {str(key): normalize_json_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [normalize_json_value(item) for item in value]

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return normalize_json_value(to_dict())

    if is_dataclass(value) and not isinstance(value, type):
        return normalize_json_value(asdict(value))

    return value


def dump_json(value: Any, **kwargs: Any) -> str:
    """在序列化前先做一次 JSON 兼容归一化。"""
    return json.dumps(normalize_json_value(value), **kwargs)
