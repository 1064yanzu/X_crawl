from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummyInstance:
    def __init__(self, instance_id: int):
        self.instance_id = instance_id
        self.closed = 0

    @property
    def is_alive(self) -> bool:
        return self.closed == 0

    def close(self) -> None:
        self.closed += 1


def test_release_auto_closes_idle_slot(monkeypatch):
    import config
    from crawler import browser_pool

    monkeypatch.setattr(config.settings, "browser_pool_auto_close_idle", True, raising=False)
    monkeypatch.setattr(browser_pool, "BrowserInstance", _DummyInstance)

    pool = browser_pool.BrowserPool(max_size=2)
    instance, slot_id = pool.acquire("task-1", platform="x")

    assert slot_id == 0
    assert pool.status()["total_slots"] == 1

    pool.release("task-1")

    assert instance.closed == 1
    assert pool.status()["total_slots"] == 0


def test_resize_prunes_extra_idle_slots_even_when_auto_close_disabled(monkeypatch):
    import config
    from crawler import browser_pool

    monkeypatch.setattr(config.settings, "browser_pool_auto_close_idle", False, raising=False)
    monkeypatch.setattr(browser_pool, "BrowserInstance", _DummyInstance)

    pool = browser_pool.BrowserPool(max_size=3)
    inst1, _ = pool.acquire("task-1", platform="x")
    inst2, _ = pool.acquire("task-2", platform="x")
    inst3, _ = pool.acquire("task-3", platform="x")

    pool.release("task-1")
    pool.release("task-2")
    pool.release("task-3")

    assert pool.status()["total_slots"] == 3

    pool.resize(1)
    status = pool.status()

    assert status["max_size"] == 1
    assert status["total_slots"] == 1
    assert sorted([inst1.closed, inst2.closed, inst3.closed]) == [0, 1, 1]


def test_acquire_prefers_exclusive_slot_before_cross_platform_sharing(monkeypatch):
    import config
    from crawler import browser_pool

    monkeypatch.setattr(config.settings, "browser_pool_auto_close_idle", False, raising=False)
    monkeypatch.setattr(browser_pool, "BrowserInstance", _DummyInstance)

    pool = browser_pool.BrowserPool(max_size=3)

    _, slot_x1 = pool.acquire("task-x-1", platform="x")
    _, slot_x2 = pool.acquire("task-x-2", platform="x")
    _, slot_weibo = pool.acquire("task-w-1", platform="weibo")

    assert (slot_x1, slot_x2, slot_weibo) == (0, 1, 2)
    assert pool.status()["total_slots"] == 3


def test_acquire_falls_back_to_cross_platform_sharing_when_pool_is_full(monkeypatch):
    import config
    from crawler import browser_pool

    monkeypatch.setattr(config.settings, "browser_pool_auto_close_idle", False, raising=False)
    monkeypatch.setattr(browser_pool, "BrowserInstance", _DummyInstance)

    pool = browser_pool.BrowserPool(max_size=2)

    _, slot_x1 = pool.acquire("task-x-1", platform="x")
    _, slot_weibo1 = pool.acquire("task-w-1", platform="weibo")
    _, slot_x2 = pool.acquire("task-x-2", platform="x")

    assert (slot_x1, slot_weibo1, slot_x2) == (0, 1, 1)
    assert pool.status()["total_slots"] == 2


def test_status_includes_aux_instance_counts(monkeypatch):
    import config
    from crawler import browser_pool

    monkeypatch.setattr(config.settings, "browser_pool_auto_close_idle", False, raising=False)
    monkeypatch.setattr(browser_pool, "BrowserInstance", _DummyInstance)

    pool = browser_pool.BrowserPool(max_size=2)
    pool.acquire("task-x-1", platform="x")
    aux = pool.acquire_aux("task-x-1", purpose="reply")

    status = pool.status()

    assert aux.instance_id >= 10000
    assert status["total_slots"] == 1
    assert status["aux_instances"] == 1
    assert status["alive_aux_instances"] == 1
    assert status["total_instances"] == 2
    assert status["alive_instances"] == 2


def test_cleanup_stale_pool_browsers_respects_max_size(monkeypatch):
    from crawler import browser_pool

    monkeypatch.setattr(
        browser_pool,
        "_iter_managed_pool_roots",
        lambda **kwargs: [
            {"pid": 101, "create_time": 1.0},
            {"pid": 102, "create_time": 2.0},
            {"pid": 103, "create_time": 3.0},
        ],
    )

    killed: list[int] = []
    monkeypatch.setattr(browser_pool, "_terminate_process_tree", lambda pid: killed.append(pid) or 1)

    result = browser_pool.cleanup_stale_pool_browsers(max_size=2)

    assert killed == [103]
    assert result["roots_seen"] == 3
    assert result["killed_roots"] == 1


def test_browser_instance_resets_profile_dir_before_launch(tmp_path, monkeypatch):
    from crawler import browser_pool

    profile = tmp_path / "instance-9"
    profile.mkdir(parents=True)
    (profile / "SingletonLock").write_text("stale", encoding="utf-8")
    (profile / "Preferences").write_text("broken", encoding="utf-8")

    inst = browser_pool.BrowserInstance(instance_id=9)
    inst.profile_dir = str(profile)
    inst._reset_profile_dir()

    assert os.path.isdir(inst.profile_dir)
    assert not (profile / "SingletonLock").exists()
    assert not (profile / "Preferences").exists()


def test_compute_pool_max_size_doubles_for_cross_platform_concurrency():
    from crawler.browser_pool import compute_pool_max_size

    assert compute_pool_max_size(3, cross_platform=True) == 6
    assert compute_pool_max_size(3, cross_platform=False) == 3


def test_browser_instance_profile_dir_is_process_scoped():
    from crawler.browser_pool import BrowserInstance

    inst = BrowserInstance(instance_id=3)

    assert "worker-" in inst.profile_dir
    assert inst.profile_dir.endswith("instance-3")


def test_is_pool_mode_enabled_when_cross_platform_single_task_enabled(monkeypatch):
    import config
    from crawler import browser_pool

    monkeypatch.setattr(config.settings, "crawler_max_concurrent_tasks", 1, raising=False)
    monkeypatch.setattr(config.settings, "crawler_cross_platform_concurrent", True, raising=False)
    assert browser_pool.is_pool_mode_enabled() is True

    monkeypatch.setattr(config.settings, "crawler_cross_platform_concurrent", False, raising=False)
    assert browser_pool.is_pool_mode_enabled() is False
