"""
query_builder 单元测试
"""
import pytest
from crawler.query_builder import build_advanced_query


class TestBuildAdvancedQuery:
    """测试高级搜索操作符构建。"""

    def test_empty_params_returns_empty(self):
        assert build_advanced_query() == ""

    def test_all_words(self):
        result = build_advanced_query(all_words="what's happening")
        assert result == "what's happening"

    def test_exact_phrase(self):
        result = build_advanced_query(exact_phrase="happy hour")
        assert result == '"happy hour"'

    def test_any_words_multiple(self):
        result = build_advanced_query(any_words="cats dogs")
        assert result == "(cats OR dogs)"

    def test_any_words_single(self):
        result = build_advanced_query(any_words="cats")
        assert result == "cats"

    def test_none_words(self):
        result = build_advanced_query(none_words="cats dogs")
        assert result == "-cats -dogs"

    def test_hashtags_with_hash(self):
        result = build_advanced_query(hashtags="#ThrowbackThursday")
        assert result == "#ThrowbackThursday"

    def test_hashtags_without_hash(self):
        result = build_advanced_query(hashtags="ThrowbackThursday")
        assert result == "#ThrowbackThursday"

    def test_language(self):
        result = build_advanced_query(lang="en")
        assert result == "lang:en"

    def test_from_accounts_single(self):
        result = build_advanced_query(from_accounts="elonmusk")
        assert result == "from:elonmusk"

    def test_from_accounts_with_at(self):
        result = build_advanced_query(from_accounts="@elonmusk")
        assert result == "from:elonmusk"

    def test_from_accounts_multiple(self):
        result = build_advanced_query(from_accounts="elonmusk jack")
        assert result == "(from:elonmusk OR from:jack)"

    def test_to_accounts(self):
        result = build_advanced_query(to_accounts="@X")
        assert result == "to:X"

    def test_mention_accounts(self):
        result = build_advanced_query(mention_accounts="SFBART Caltrain")
        assert result == "@SFBART @Caltrain"

    def test_mention_accounts_with_at(self):
        result = build_advanced_query(mention_accounts="@SFBART")
        assert result == "@SFBART"

    def test_reply_filter_only(self):
        result = build_advanced_query(reply_filter="only")
        assert result == "filter:replies"

    def test_reply_filter_off(self):
        result = build_advanced_query(reply_filter="off")
        assert result == ""

    def test_link_filter_only(self):
        result = build_advanced_query(link_filter="only")
        assert result == "filter:links"

    def test_engagement_min_replies(self):
        result = build_advanced_query(min_replies=280)
        assert result == "min_replies:280"

    def test_engagement_min_faves(self):
        result = build_advanced_query(min_faves=1000)
        assert result == "min_faves:1000"

    def test_engagement_min_retweets(self):
        result = build_advanced_query(min_retweets=500)
        assert result == "min_retweets:500"

    def test_engagement_zero_ignored(self):
        result = build_advanced_query(min_faves=0)
        assert result == ""

    def test_date_since(self):
        result = build_advanced_query(since="2024-01-01")
        assert result == "since:2024-01-01"

    def test_date_until(self):
        result = build_advanced_query(until="2024-12-31")
        assert result == "until:2024-12-31"

    def test_combined_query(self):
        result = build_advanced_query(
            all_words="AI",
            exact_phrase="machine learning",
            none_words="广告",
            from_accounts="elonmusk",
            min_faves=1000,
            lang="en",
            since="2024-01-01",
            until="2024-12-31",
        )
        assert '"machine learning"' in result
        assert "from:elonmusk" in result
        assert "min_faves:1000" in result
        assert "lang:en" in result
        assert "since:2024-01-01" in result
        assert "until:2024-12-31" in result
        assert "-广告" in result
        assert "AI" in result

    def test_whitespace_handling(self):
        """空白字符串应被忽略。"""
        result = build_advanced_query(all_words="  ", exact_phrase="  ", lang="")
        assert result == ""

    def test_comma_separated_accounts(self):
        """逗号分隔的账号也应正确解析。"""
        result = build_advanced_query(from_accounts="user1,user2,user3")
        assert result == "(from:user1 OR from:user2 OR from:user3)"
