from api.services.task_insights import summarize_tweets


def test_summarize_tweets_time_coverage_and_reply_count():
    tweets = [
        {
            "id": "t1",
            "created_at": "2026-02-20T10:00:00+00:00",
            "replies": [
                {"id": "r1", "created_at": "2026-02-20T11:00:00+00:00"},
                {"id": "r2", "created_at": "2026-02-20T12:00:00+00:00"},
            ],
        },
        {
            "id": "t2",
            "created_at": "2026-02-22T10:00:00+00:00",
            "replies": [
                {"id": "r3", "created_at": "2026-02-22T10:30:00+00:00"},
            ],
        },
    ]

    replies, coverage = summarize_tweets(tweets)

    assert replies == 3
    assert coverage["tweet_start_at"] == "2026-02-20T10:00:00+00:00"
    assert coverage["tweet_end_at"] == "2026-02-22T10:00:00+00:00"
    assert coverage["reply_start_at"] == "2026-02-20T11:00:00+00:00"
    assert coverage["reply_end_at"] == "2026-02-22T10:30:00+00:00"
    assert coverage["combined_start_at"] == "2026-02-20T10:00:00+00:00"
    assert coverage["combined_end_at"] == "2026-02-22T10:30:00+00:00"
