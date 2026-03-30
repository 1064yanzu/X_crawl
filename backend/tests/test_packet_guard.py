from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.packet_guard import has_search_results_entries, is_contentful_search_timeline_body


def _build_body(entries: list[dict]) -> dict:
    return {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {
                    "timeline": {
                        "instructions": [
                            {
                                "type": "TimelineAddEntries",
                                "entries": entries,
                            }
                        ]
                    }
                }
            }
        }
    }


def test_cursor_only_search_timeline_is_not_contentful():
    body = _build_body(
        [
            {
                "entryId": "cursor-top",
                "content": {
                    "__typename": "TimelineTimelineCursor",
                    "cursorType": "Top",
                    "value": "top-cursor",
                },
            },
            {
                "entryId": "cursor-bottom",
                "content": {
                    "__typename": "TimelineTimelineCursor",
                    "cursorType": "Bottom",
                    "value": "bottom-cursor",
                },
            },
        ]
    )

    assert has_search_results_entries(body) is False
    assert is_contentful_search_timeline_body(body) is False


def test_search_timeline_item_with_tweet_is_contentful():
    body = _build_body(
        [
            {
                "entryId": "tweet-1",
                "content": {
                    "__typename": "TimelineTimelineItem",
                    "itemContent": {
                        "__typename": "TimelineTweet",
                    },
                },
            }
        ]
    )

    assert has_search_results_entries(body) is True
    assert is_contentful_search_timeline_body(body) is True


def test_search_timeline_module_with_tweet_is_contentful():
    body = _build_body(
        [
            {
                "entryId": "module-1",
                "content": {
                    "__typename": "TimelineTimelineModule",
                    "items": [
                        {
                            "item": {
                                "itemContent": {
                                    "__typename": "TimelineTweet",
                                }
                            }
                        }
                    ],
                },
            }
        ]
    )

    assert has_search_results_entries(body) is True
    assert is_contentful_search_timeline_body(body) is True
