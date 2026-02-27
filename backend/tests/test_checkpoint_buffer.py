import crawler.checkpoint_buffer as checkpoint_buffer


def test_stage_reply_checkpoint_flushes_on_batch(monkeypatch):
    task_id = "task-batch"
    checkpoint_buffer.clear_reply_checkpoint(task_id)
    calls: list[dict] = []

    monkeypatch.setattr(checkpoint_buffer.settings, "crawler_checkpoint_reply_batch", 2)
    monkeypatch.setattr(checkpoint_buffer.settings, "crawler_checkpoint_flush_interval_sec", 999.0)
    monkeypatch.setattr(checkpoint_buffer, "save_checkpoint", lambda **kwargs: calls.append(kwargs))

    flushed = checkpoint_buffer.stage_reply_checkpoint(
        task_id=task_id,
        keyword="k",
        product="Top",
        tweets_so_far=[{"id": "1"}],
        next_cursor="c1",
        page_fetched=1,
    )
    assert flushed is False
    assert len(calls) == 0

    flushed = checkpoint_buffer.stage_reply_checkpoint(
        task_id=task_id,
        keyword="k",
        product="Top",
        tweets_so_far=[{"id": "1"}, {"id": "2"}],
        next_cursor="c2",
        page_fetched=1,
    )
    assert flushed is True
    assert len(calls) == 1
    assert calls[0]["next_cursor"] == "c2"
    checkpoint_buffer.clear_reply_checkpoint(task_id)


def test_stage_reply_checkpoint_flushes_on_interval(monkeypatch):
    task_id = "task-interval"
    checkpoint_buffer.clear_reply_checkpoint(task_id)
    calls: list[dict] = []
    now = {"v": 0.0}

    monkeypatch.setattr(checkpoint_buffer.settings, "crawler_checkpoint_reply_batch", 999)
    monkeypatch.setattr(checkpoint_buffer.settings, "crawler_checkpoint_flush_interval_sec", 1.0)
    monkeypatch.setattr(checkpoint_buffer.time, "monotonic", lambda: now["v"])
    monkeypatch.setattr(checkpoint_buffer, "save_checkpoint", lambda **kwargs: calls.append(kwargs))

    flushed = checkpoint_buffer.stage_reply_checkpoint(
        task_id=task_id,
        keyword="k",
        product="Top",
        tweets_so_far=[{"id": "1"}],
        next_cursor="c1",
        page_fetched=1,
    )
    assert flushed is False
    assert len(calls) == 0

    now["v"] = 1.2
    flushed = checkpoint_buffer.stage_reply_checkpoint(
        task_id=task_id,
        keyword="k",
        product="Top",
        tweets_so_far=[{"id": "1"}, {"id": "2"}],
        next_cursor="c2",
        page_fetched=1,
    )
    assert flushed is True
    assert len(calls) == 1
    assert calls[0]["tweets_so_far"][-1]["id"] == "2"
    checkpoint_buffer.clear_reply_checkpoint(task_id)

