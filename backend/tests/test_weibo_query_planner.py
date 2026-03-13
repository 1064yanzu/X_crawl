from crawler.weibo.query_planner import build_weibo_query_plan


def test_single_keyword_keeps_original_query() -> None:
    plan = build_weibo_query_plan("Claude")

    assert plan.variants == ("Claude",)
    assert plan.uses_or_split is False


def test_simple_or_query_is_split_into_variants() -> None:
    plan = build_weibo_query_plan("Claude OR anthropic")

    assert plan.variants == ("Claude", "anthropic")
    assert plan.uses_or_split is True


def test_parenthesized_or_query_is_split() -> None:
    plan = build_weibo_query_plan("(Claude OR anthropic OR MCP)")

    assert plan.variants == ("Claude", "anthropic", "MCP")
    assert plan.uses_or_split is True


def test_nested_parentheses_do_not_split_non_top_level_or() -> None:
    plan = build_weibo_query_plan("AI (Claude OR anthropic)")

    assert plan.variants == ("AI (Claude OR anthropic)",)
    assert plan.uses_or_split is False


def test_or_inside_quotes_is_not_split() -> None:
    plan = build_weibo_query_plan('\"Claude OR anthropic\"')

    assert plan.variants == ('\"Claude OR anthropic\"',)
    assert plan.uses_or_split is False


def test_or_query_keeps_original_when_split_disabled() -> None:
    plan = build_weibo_query_plan("Claude OR anthropic", enable_or_split=False)

    assert plan.variants == ("Claude OR anthropic",)
    assert plan.uses_or_split is False
