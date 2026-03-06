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


def test_build_time_split_plan_for_limited_mode_short_span():
    """跨度 < 90 天时，仍使用配置的 window_days（14天）"""
    plan = build_time_split_plan(
        "AI since:2024-01-01 until:2024-02-20",
        max_count=500,
        enabled=True,
        trigger_days=10,
        window_days=14,
        unlimited_window_days=7,
        max_segments=20,
    )
    assert plan.enabled is True
    assert len(plan.segments) > 1
    # 短跨度使用固定 14 天窗口
    assert serialize_segments(plan.segments)[0] == {"since": "2024-01-01", "until": "2024-01-15"}


def test_build_time_split_plan_for_unlimited_mode_short_span():
    """跨度 < 90 天 + 无上限模式，使用配置的 unlimited_window_days（7天）"""
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


def test_build_time_split_plan_long_span_uses_monthly_split():
    """跨度 ≥ 90 天时，自动升级为按月分割"""
    plan = build_time_split_plan(
        "AI since:2024-01-01 until:2024-06-01",
        max_count=500,
        enabled=True,
        trigger_days=30,
        window_days=14,
        unlimited_window_days=7,
        max_segments=120,
    )
    assert plan.enabled is True
    # 5个月 = 5 个 segment（1月→2月, 2月→3月, ...5月→6月）
    assert len(plan.segments) == 5
    segs = serialize_segments(plan.segments)
    assert segs[0] == {"since": "2024-01-01", "until": "2024-02-01"}
    assert segs[1] == {"since": "2024-02-01", "until": "2024-03-01"}
    assert segs[4] == {"since": "2024-05-01", "until": "2024-06-01"}


def test_build_time_split_plan_multi_year_span():
    """跨越多年的任务应该按月分割，分段数可控"""
    plan = build_time_split_plan(
        "AI since:2020-01-01 until:2025-01-01",
        max_count=0,
        enabled=True,
        trigger_days=30,
        window_days=14,
        unlimited_window_days=7,
        max_segments=120,
    )
    assert plan.enabled is True
    # 5 年 = 60 个月 = 60 个 segment（远少于旧算法的 260 段）
    assert len(plan.segments) == 60
    segs = serialize_segments(plan.segments)
    assert segs[0] == {"since": "2020-01-01", "until": "2020-02-01"}
    assert segs[-1] == {"since": "2024-12-01", "until": "2025-01-01"}


def test_build_time_split_plan_multi_year_max_segments_cap():
    """跨越极长时间时，max_segments 仍然生效"""
    plan = build_time_split_plan(
        "AI since:2010-01-01 until:2025-01-01",
        max_count=0,
        enabled=True,
        trigger_days=30,
        window_days=14,
        unlimited_window_days=7,
        max_segments=50,
    )
    assert plan.enabled is True
    # 15 年 = 180 个月，但 max_segments=50 限制了上限
    assert len(plan.segments) == 50


def test_build_time_split_plan_mid_month_start():
    """从月中开始的按月分割，保证对齐"""
    plan = build_time_split_plan(
        "AI since:2024-01-15 until:2024-06-01",
        max_count=500,
        enabled=True,
        trigger_days=30,
        window_days=14,
        unlimited_window_days=7,
        max_segments=120,
    )
    assert plan.enabled is True
    segs = serialize_segments(plan.segments)
    # 从 1-15 开始，按月递进
    assert segs[0] == {"since": "2024-01-15", "until": "2024-02-15"}
    assert segs[1] == {"since": "2024-02-15", "until": "2024-03-15"}


def test_build_time_split_plan_disabled():
    """功能关闭时不分割"""
    plan = build_time_split_plan(
        "AI since:2020-01-01 until:2025-01-01",
        max_count=0,
        enabled=False,
        trigger_days=30,
        window_days=14,
        unlimited_window_days=7,
        max_segments=120,
    )
    assert plan.enabled is False
    assert len(plan.segments) == 0
