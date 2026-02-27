from crawler import telemetry


def test_telemetry_snapshot_and_rate() -> None:
    task_id = "telemetry-task-1"
    telemetry.clear_task(task_id)

    telemetry.init_task(task_id, status="pending", phase="init")
    telemetry.record_event(task_id, "progress", delta_tweets=5, delta_replies=2, status="running")

    snap = telemetry.get_snapshot(task_id, queue_position=2)
    assert snap["events_total"] >= 2
    assert snap["last_event_id"] >= 2
    assert snap["tweets_per_min_15s"] > 0
    assert snap["replies_per_min_15s"] > 0
    assert snap["queue_position"] == 2


def test_telemetry_events_since() -> None:
    task_id = "telemetry-task-2"
    telemetry.clear_task(task_id)

    telemetry.init_task(task_id)
    e1 = telemetry.record_event(task_id, "phase", phase="A")
    e2 = telemetry.record_event(task_id, "phase", phase="B")

    assert e1 is not None and e2 is not None

    events = telemetry.get_events_since(task_id, after_id=int(e1["id"]))
    assert len(events) == 1
    assert events[0]["phase"] == "B"

    latest = telemetry.get_latest_action(task_id)
    assert latest is not None
    assert latest["phase"] == "B"
