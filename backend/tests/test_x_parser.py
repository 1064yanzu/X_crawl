from crawler.parser import parse_search_response


def _tweet_result(tweet_id: str, screen_name: str, text: str) -> dict:
    return {
        "__typename": "Tweet",
        "rest_id": tweet_id,
        "source": '<a href="https://x.com" rel="nofollow">X Web App</a>',
        "core": {
            "user_results": {
                "result": {
                    "__typename": "User",
                    "rest_id": f"user-{tweet_id}",
                    "core": {"name": screen_name.title(), "screen_name": screen_name},
                    "legacy": {
                        "name": screen_name.title(),
                        "screen_name": screen_name,
                        "description": "",
                        "entities": {},
                        "followers_count": 1,
                        "friends_count": 2,
                        "statuses_count": 3,
                        "favourites_count": 4,
                        "media_count": 5,
                        "listed_count": 6,
                        "created_at": "Wed Mar 26 08:00:00 +0000 2026",
                        "is_translator": False,
                        "has_custom_timelines": False,
                        "pinned_tweet_ids_str": [],
                        "profile_image_url_https": "https://example.com/avatar_normal.jpg",
                    },
                    "avatar": {"image_url": "https://example.com/avatar.jpg"},
                    "privacy": {"protected": False},
                }
            }
        },
        "legacy": {
            "id_str": tweet_id,
            "conversation_id_str": tweet_id,
            "full_text": text,
            "display_text_range": [0, len(text)],
            "created_at": "Wed Mar 26 08:00:00 +0000 2026",
            "lang": "en",
            "favorite_count": 10,
            "retweet_count": 11,
            "reply_count": 12,
            "quote_count": 13,
            "bookmark_count": 14,
            "possibly_sensitive": False,
            "entities": {
                "hashtags": [],
                "symbols": [],
                "urls": [],
                "user_mentions": [],
            },
        },
        "views": {"count": "123", "state": "Enabled"},
        "edit_control": {"is_edit_eligible": False, "edits_remaining": "0"},
    }


def test_parse_search_response_supports_replace_entry_and_module_tweets():
    payload = {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {
                    "timeline": {
                        "instructions": [
                            {
                                "type": "TimelineAddEntries",
                                "entries": [
                                    {
                                        "entryId": "tweet-1",
                                        "content": {
                                            "__typename": "TimelineTimelineItem",
                                            "itemContent": {
                                                "__typename": "TimelineTweet",
                                                "tweet_results": {"result": _tweet_result("1", "alice", "hello world")},
                                                "highlights": {
                                                    "textHighlights": [{"startIndex": 0, "endIndex": 5}]
                                                },
                                            },
                                        },
                                    },
                                    {
                                        "entryId": "cursor-bottom-1",
                                        "content": {
                                            "__typename": "TimelineTimelineCursor",
                                            "cursorType": "Bottom",
                                            "value": "BOTTOM-1",
                                        },
                                    },
                                ],
                            },
                            {
                                "type": "TimelineReplaceEntry",
                                "entry": {
                                    "entryId": "cursor-top-1",
                                    "content": {
                                        "__typename": "TimelineTimelineCursor",
                                        "cursorType": "Top",
                                        "value": "TOP-1",
                                    },
                                },
                            },
                            {
                                "type": "TimelineAddEntries",
                                "entries": [
                                    {
                                        "entryId": "module-1",
                                        "content": {
                                            "__typename": "TimelineTimelineModule",
                                            "items": [
                                                {
                                                    "entryId": "module-1-tweet-2",
                                                    "item": {
                                                        "itemContent": {
                                                            "__typename": "TimelineTweet",
                                                            "tweet_results": {
                                                                "result": _tweet_result("2", "bob", "module tweet")
                                                            },
                                                        }
                                                    },
                                                },
                                                {
                                                    "entryId": "module-1-user-1",
                                                    "item": {
                                                        "itemContent": {
                                                            "__typename": "TimelineUser",
                                                            "user_results": {"result": {}},
                                                        }
                                                    },
                                                },
                                            ],
                                        },
                                    }
                                ],
                            },
                        ]
                    }
                }
            }
        }
    }

    tweets, bottom_cursor, top_cursor = parse_search_response(payload)

    assert [tweet["id"] for tweet in tweets] == ["1", "2"]
    assert tweets[0]["text_highlights"] == [{"start": 0, "end": 5}]
    assert tweets[1]["text"] == "module tweet"
    assert bottom_cursor == "BOTTOM-1"
    assert top_cursor == "TOP-1"


def test_parse_search_response_ignores_non_tweet_items():
    payload = {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {
                    "timeline": {
                        "instructions": [
                            {
                                "type": "TimelineAddEntries",
                                "entries": [
                                    {
                                        "entryId": "prompt-1",
                                        "content": {
                                            "__typename": "TimelineTimelineItem",
                                            "itemContent": {"__typename": "TimelinePrompt"},
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                }
            }
        }
    }

    tweets, bottom_cursor, top_cursor = parse_search_response(payload)

    assert tweets == []
    assert bottom_cursor is None
    assert top_cursor is None
