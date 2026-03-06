from crawler.x_time_splitter import (
    build_query_with_window,
    build_time_split_plan,
    parse_query_time_range,
    serialize_segments,
)


def test_parse_query_time_range_preserves_other_operators():
    base_query, since, until = parse_query_time_range(
        'ChatGPT from:openai min_faves:100 since:2024-01-01 until:2024-03-01'
    )
    assert base_query == "ChatGPT from:openai min_faves:100"
    assert since == "2024-01-01"
    assert until == "2024-03-01"


def test_build_time_split_plan_for_limited_mode():
    plan = build_time_split_plan(
        "AI since:2024-01-01 until:2024-03-15",
        max_count=500,
        enabled=True,
        trigger_days=10,
        window_days=14,
        unlimited_window_days=7,
        max_segments=20,
    )
    assert plan.enabled is True
    assert len(plan.segments) > 1
    assert serialize_segments(plan.segments)[0] == {"since": "2024-01-01", "until": "2024-01-15"}


def test_build_time_split_plan_for_unlimited_mode_uses_smaller_window():
    plan = build_time_split_plan(
        "AI since:2024-01-01 until:2024-01-25",
        max_count=0,
        enabled=True,
        trigger_days=5,
        window_days=14,
        unlimited_window_days=7,
        max_segments=20,
    )
    assert plan.enabled is True
    assert len(plan.segments) == 4
    assert build_query_with_window(plan.base_query, plan.segments[0].since, plan.segments[0].until).endswith(
        "since:2024-01-01 until:2024-01-08"
    )
