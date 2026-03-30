from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_x_account_worker_limit_respects_active_accounts(monkeypatch):
    import config
    from api.services.task_scheduler import TaskScheduler

    class _DummyPool:
        def get_active_account_count(self) -> int:
            return 3

    scheduler = TaskScheduler()
    monkeypatch.setattr(config.settings, "crawler_max_concurrent_tasks", 5, raising=False)
    monkeypatch.setattr(config.settings, "account_pool_enabled", True, raising=False)

    from crawler import account_pool
    monkeypatch.setattr(account_pool, "get_pool", lambda: _DummyPool())

    assert scheduler._x_account_worker_limit() == 3


def test_x_account_worker_limit_falls_back_when_account_pool_disabled(monkeypatch):
    import config
    from api.services.task_scheduler import TaskScheduler

    scheduler = TaskScheduler()
    monkeypatch.setattr(config.settings, "crawler_max_concurrent_tasks", 4, raising=False)
    monkeypatch.setattr(config.settings, "account_pool_enabled", False, raising=False)

    assert scheduler._x_account_worker_limit() == 4


def test_x_account_worker_limit_subtracts_reserved_paused_accounts(monkeypatch):
    import config
    from api.services.task_scheduler import TaskScheduler

    class _DummyPool:
        def get_active_account_count(self) -> int:
            return 3

    class _DummyDispatcher:
        def active_assignment_count(self) -> int:
            return 2

    scheduler = TaskScheduler()
    monkeypatch.setattr(config.settings, "crawler_max_concurrent_tasks", 5, raising=False)
    monkeypatch.setattr(config.settings, "account_pool_enabled", True, raising=False)
    monkeypatch.setattr(scheduler, "_platform_running_count", lambda platform: 0 if platform == "x" else 0)

    from crawler import account_pool, account_dispatcher
    monkeypatch.setattr(account_pool, "get_pool", lambda: _DummyPool())
    monkeypatch.setattr(account_dispatcher, "get_dispatcher", lambda: _DummyDispatcher())

    assert scheduler._x_account_worker_limit() == 1
