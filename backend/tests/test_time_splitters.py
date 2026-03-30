from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_x_time_splitter_uses_fixed_seven_day_windows_for_long_span() -> None:
    from crawler.x_time_splitter import build_time_split_plan

    plan = build_time_split_plan(
        "OpenAI since:2022-06-01 until:2022-06-23",
        max_count=100,
        enabled=True,
        trigger_days=7,
        window_days=7,
        unlimited_window_days=7,
        max_segments=20,
    )

    assert plan.enabled is True
    assert plan.window_days == 7
    assert [(seg.since, seg.until) for seg in plan.segments] == [
        ("2022-06-01", "2022-06-08"),
        ("2022-06-08", "2022-06-15"),
        ("2022-06-15", "2022-06-22"),
        ("2022-06-22", "2022-06-23"),
    ]


def test_x_time_splitter_raises_when_required_segments_exceed_limit() -> None:
    from crawler.x_time_splitter import build_time_split_plan

    with pytest.raises(ValueError, match="超过安全上限"):
        build_time_split_plan(
            "OpenAI since:2022-06-01 until:2022-10-25",
            max_count=0,
            enabled=True,
            trigger_days=7,
            window_days=7,
            unlimited_window_days=7,
            max_segments=10,
        )


def test_x_time_splitter_forces_seven_day_windows_when_span_exceeds_one_year() -> None:
    from crawler.x_time_splitter import build_time_split_plan

    plan = build_time_split_plan(
        "OpenAI since:2022-06-01 until:2024-01-01",
        max_count=100,
        enabled=True,
        trigger_days=30,
        window_days=14,
        unlimited_window_days=21,
        max_segments=200,
    )

    assert plan.enabled is True
    assert plan.window_days == 7
    assert (plan.segments[0].since, plan.segments[0].until) == ("2022-06-01", "2022-06-08")


def test_x_time_splitter_long_span_ignores_legacy_small_segment_limit() -> None:
    from crawler.x_time_splitter import build_time_split_plan

    plan = build_time_split_plan(
        "OpenAI since:2022-06-01 until:2026-03-25",
        max_count=100,
        enabled=True,
        trigger_days=30,
        window_days=14,
        unlimited_window_days=14,
        max_segments=120,
    )

    assert plan.enabled is True
    assert plan.window_days == 7
    assert len(plan.segments) > 120


def test_weibo_date_splitter_uses_fixed_seven_day_windows_for_long_span() -> None:
    from crawler.weibo.date_splitter import split_date_range

    ranges = split_date_range(
        "2022-06-01",
        "2022-06-23",
        window_days=7,
        max_segments=20,
    )

    assert ranges == [
        ("2022-06-01", "2022-06-07"),
        ("2022-06-08", "2022-06-14"),
        ("2022-06-15", "2022-06-21"),
        ("2022-06-22", "2022-06-23"),
    ]


def test_weibo_date_splitter_raises_when_required_segments_exceed_limit() -> None:
    from crawler.weibo.date_splitter import split_date_range

    with pytest.raises(ValueError, match="超过安全上限"):
        split_date_range(
            "2022-06-01",
            "2026-03-25",
            window_days=7,
            max_segments=10,
        )
