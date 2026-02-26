import threading
import time

from api.services import task_scheduler
from api.services.task_scheduler import MemoryQueueBackend, ScheduledTask, TaskScheduler


def test_memory_queue_backend_put_get():
    backend = MemoryQueueBackend()
    item = ScheduledTask(task_id="t1", payload={"k": "v"})
    backend.put(item)
    assert backend.size() == 1
    got = backend.get(timeout=0.1)
    assert got is not None
    assert got.task_id == "t1"


def test_scheduler_dispatch_and_deduplicate(monkeypatch):
    monkeypatch.setattr(task_scheduler.settings, "crawler_max_concurrent_tasks", 1)
    sched = TaskScheduler()
    fired = threading.Event()

    def executor(task_id: str, payload: dict) -> threading.Thread:
        def _run():
            time.sleep(0.05)
            fired.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    sched.register_executor(executor)
    assert sched.enqueue("task-a", {"x": 1}) is True
    assert sched.enqueue("task-a", {"x": 2}) is False
    assert fired.wait(1.0) is True
    sched.mark_done("task-a")
    assert sched.is_running("task-a") is False

