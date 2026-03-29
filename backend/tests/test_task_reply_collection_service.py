from api.services import task_reply_collection_service


class _FakeTaskManager:
    def __init__(self, tasks: dict[str, dict]):
        self._tasks = tasks
        self.updated: list[dict] = []

    def get_task_summary(self, task_id: str):
        return self._tasks.get(task_id)

    def update_task_reply_collection_config(self, task_id: str, *, fetch_replies: bool, reply_depth: int):
        task = self._tasks.get(task_id)
        if not task:
            return False
        task["fetch_replies"] = fetch_replies
        task["reply_depth"] = reply_depth
        self.updated.append(
            {
                "task_id": task_id,
                "fetch_replies": fetch_replies,
                "reply_depth": reply_depth,
            }
        )
        return True


def test_batch_update_reply_collection_enable_second_level_comments(monkeypatch):
    tasks = {
        "task-a": {
            "task_id": "task-a",
            "task_kind": "search",
            "platform": "x",
            "status": "done",
            "fetch_replies": False,
            "reply_depth": 1,
        },
        "task-b": {
            "task_id": "task-b",
            "task_kind": "search",
            "platform": "x",
            "status": "failed",
            "fetch_replies": True,
            "reply_depth": 1,
        },
        "task-c": {
            "task_id": "task-c",
            "task_kind": "search",
            "platform": "weibo",
            "status": "done",
            "fetch_replies": False,
            "reply_depth": 1,
        },
    }
    fake_tm = _FakeTaskManager(tasks)
    monkeypatch.setattr(task_reply_collection_service, "_get_task_manager", lambda: fake_tm)

    result = task_reply_collection_service.batch_update_reply_collection(
        ["task-a", "task-b", "task-c"],
        "with_comments",
    )

    assert result["updated_task_ids"] == ["task-a", "task-b", "task-c"]
    assert result["mode"] == "with_comments"
    assert fake_tm.updated == [
        {"task_id": "task-a", "fetch_replies": True, "reply_depth": 2},
        {"task_id": "task-b", "fetch_replies": True, "reply_depth": 2},
        {"task_id": "task-c", "fetch_replies": True, "reply_depth": 2},
    ]
    assert result["skipped"] == []


def test_batch_update_reply_collection_skip_active_and_already_disabled(monkeypatch):
    tasks = {
        "task-a": {
            "task_id": "task-a",
            "task_kind": "search",
            "platform": "x",
            "status": "running",
            "fetch_replies": True,
            "reply_depth": 2,
        },
        "task-b": {
            "task_id": "task-b",
            "task_kind": "search",
            "platform": "x",
            "status": "done",
            "fetch_replies": False,
            "reply_depth": 1,
        },
        "task-c": {
            "task_id": "task-c",
            "task_kind": "comment_backfill",
            "platform": "x",
            "status": "done",
            "fetch_replies": True,
            "reply_depth": 2,
        },
    }
    fake_tm = _FakeTaskManager(tasks)
    monkeypatch.setattr(task_reply_collection_service, "_get_task_manager", lambda: fake_tm)

    result = task_reply_collection_service.batch_update_reply_collection(
        ["task-a", "task-b", "task-c"],
        "without_comments",
    )

    assert result["updated_task_ids"] == []
    assert fake_tm.updated == []
    assert result["skipped"] == [
        {"task_id": "task-a", "reason": "仅已完成/已停止/已失败任务可修改"},
        {"task_id": "task-b", "reason": "该任务当前已是不采集评论模式"},
        {"task_id": "task-c", "reason": "仅帖子采集任务支持切换采评模式"},
    ]
