"""
账号分配器 - 管理账号与任务的绑定关系

功能：
- 为任务分配可用账号
- 跟踪账号的使用状态
- 释放账号供后续任务使用
- 处理账号限速和失效情况
"""
import logging
import threading
import time
from typing import Optional
from dataclasses import dataclass

from crawler.account_pool import get_pool, AccountEntry

logger = logging.getLogger(__name__)


@dataclass
class AccountAssignment:
    """账号分配记录"""
    account_id: str
    account_alias: str
    task_id: str
    assigned_at: float
    released_at: Optional[float] = None

    @property
    def is_active(self) -> bool:
        """是否仍在使用中"""
        return self.released_at is None

    @property
    def duration_sec(self) -> float:
        """使用时长（秒）"""
        end = self.released_at or time.time()
        return end - self.assigned_at


class AccountDispatcher:
    """账号分配器 - 线程安全"""

    def __init__(self):
        self._lock = threading.RLock()
        self._assignments: dict[str, AccountAssignment] = {}  # task_id -> assignment
        self._account_tasks: dict[str, str] = {}  # account_id -> task_id（当前任务）
        self._strategy = "round_robin"  # 分配策略
        self._rr_index = 0  # 轮询指针

    @staticmethod
    def _list_accounts(pool) -> list[AccountEntry]:
        """
        同时兼容新旧账号池接口。

        新接口是 `list_accounts()`，旧链路和部分测试桩仍使用 `get_all_accounts()`。
        """
        if hasattr(pool, "get_all_accounts"):
            return list(pool.get_all_accounts())
        if hasattr(pool, "list_accounts"):
            return list(pool.list_accounts())
        return []

    def assign_account(self, task_id: str) -> Optional[AccountEntry]:
        """
        为任务分配一个可用账号。

        返回：
            AccountEntry: 分配的账号
            None: 没有可用账号
        """
        with self._lock:
            # 检查任务是否已分配
            if task_id in self._assignments:
                assignment = self._assignments[task_id]
                if assignment.is_active:
                    pool = get_pool()
                    return pool.get_account(assignment.account_id)
                # 已释放，允许重新分配

            pool = get_pool()
            accounts = self._list_accounts(pool)

            if not accounts:
                logger.warning(f"没有可用账号来分配任务 {task_id}")
                return None

            # 过滤出未被占用且有效的账号
            available = [
                acc for acc in accounts
                if acc.enabled
                and not acc.is_rate_limited
                and acc.account_id not in self._account_tasks
            ]

            if not available:
                logger.debug(f"所有账号都被占用或限速，任务 {task_id} 等待中...")
                return None

            # 选择账号
            if self._strategy == "round_robin":
                selected = None
                total = len(accounts)
                start = self._rr_index % total if total > 0 else 0
                for offset in range(total):
                    idx = (start + offset) % total
                    candidate = accounts[idx]
                    if candidate.account_id in self._account_tasks:
                        continue
                    if not candidate.enabled or candidate.is_rate_limited:
                        continue
                    selected = candidate
                    self._rr_index = idx + 1
                    break
                if selected is None:
                    logger.debug(f"轮询后无可用账号，任务 {task_id} 等待中...")
                    return None
            else:  # least_used
                selected = min(available, key=lambda a: a.use_count)

            # 记录分配
            self._account_tasks[selected.account_id] = task_id
            self._assignments[task_id] = AccountAssignment(
                account_id=selected.account_id,
                account_alias=selected.alias,
                task_id=task_id,
                assigned_at=time.time(),
            )

            logger.info(
                f"为任务 {task_id[:8]} 分配账号 {selected.alias} ({selected.account_id[:8]})"
            )
            return selected

    def reserve_account(self, task_id: str, account_id: str) -> Optional[AccountEntry]:
        """
        预留已绑定的指定账号。

        用于任务状态里已经保存了 assigned_account_id，但当前进程内的 dispatcher
        尚未建立占用关系时，把该账号重新标记为“被这个任务独占”。
        """
        with self._lock:
            if task_id in self._assignments:
                assignment = self._assignments[task_id]
                if assignment.is_active and assignment.account_id == account_id:
                    return get_pool().get_account(account_id)

            occupied_by = self._account_tasks.get(account_id)
            if occupied_by and occupied_by != task_id:
                logger.warning(
                    f"账号 {account_id[:8]} 已被任务 {occupied_by[:8]} 占用，无法预留给任务 {task_id[:8]}"
                )
                return None

            account = get_pool().get_account(account_id)
            if not account or not account.enabled or account.is_rate_limited:
                return None

            self._account_tasks[account_id] = task_id
            self._assignments[task_id] = AccountAssignment(
                account_id=account.account_id,
                account_alias=account.alias,
                task_id=task_id,
                assigned_at=time.time(),
            )
            logger.info(
                f"为任务 {task_id[:8]} 预留已绑定账号 {account.alias} ({account.account_id[:8]})"
            )
            return account

    def release_account(self, task_id: str) -> bool:
        """
        释放任务占用的账号。

        返回：
            bool: 是否成功释放
        """
        with self._lock:
            if task_id not in self._assignments:
                return False

            assignment = self._assignments[task_id]
            if not assignment.is_active:
                return False

            account_id = assignment.account_id
            assignment.released_at = time.time()

            if account_id in self._account_tasks:
                del self._account_tasks[account_id]

            logger.info(
                f"释放账号 {assignment.account_alias} ({account_id[:8]})，"
                f"使用时长 {assignment.duration_sec:.1f}s"
            )
            return True

    def get_assignment(self, task_id: str) -> Optional[AccountAssignment]:
        """获取任务的账号分配记录"""
        with self._lock:
            return self._assignments.get(task_id)

    def get_account_for_task(self, task_id: str) -> Optional[AccountEntry]:
        """获取任务当前使用的账号"""
        with self._lock:
            assignment = self._assignments.get(task_id)
            if not assignment or not assignment.is_active:
                return None

            pool = get_pool()
            return pool.get_account(assignment.account_id)

    def get_active_assignments(self) -> list[AccountAssignment]:
        """获取所有活跃的分配记录"""
        with self._lock:
            return [a for a in self._assignments.values() if a.is_active]

    def active_assignment_count(self) -> int:
        with self._lock:
            return sum(1 for a in self._assignments.values() if a.is_active)

    def get_account_status(self) -> dict:
        """获取账号分配状态"""
        with self._lock:
            pool = get_pool()
            accounts = self._list_accounts(pool)

            status = {
                "total_accounts": len(accounts),
                "active_assignments": len(self._account_tasks),
                "accounts": [],
            }

            for acc in accounts:
                task_id = self._account_tasks.get(acc.account_id)
                status["accounts"].append({
                    "account_id": acc.account_id,
                    "alias": acc.alias,
                    "enabled": acc.enabled,
                    "is_rate_limited": acc.is_rate_limited,
                    "current_task_id": task_id,
                    "use_count": acc.use_count,
                    "fail_count": acc.fail_count,
                })

            return status

    def assign_multiple_accounts(self, task_id: str, count: int) -> list[AccountEntry]:
        """
        为一个逻辑任务分配最多 count 个账号。

        使用合成 sub-task ID（{task_id}__w0, {task_id}__w1, ...）注册到
        _account_tasks 映射中，保持 account_id → task_key 的 1:1 不变量。

        返回：
            list[AccountEntry]: 成功分配的账号列表（可能少于 count）
        """
        results: list[AccountEntry] = []
        with self._lock:
            pool = get_pool()
            accounts = self._list_accounts(pool)
            if not accounts:
                return results

            available = [
                acc for acc in accounts
                if acc.enabled
                and not acc.is_rate_limited
                and acc.account_id not in self._account_tasks
            ]

            for i in range(min(count, len(available))):
                selected = available[i]
                sub_key = f"{task_id}__w{i}"
                self._account_tasks[selected.account_id] = sub_key
                self._assignments[sub_key] = AccountAssignment(
                    account_id=selected.account_id,
                    account_alias=selected.alias,
                    task_id=sub_key,
                    assigned_at=time.time(),
                )
                results.append(selected)
                logger.info(
                    "为任务组 %s 分配账号 [worker %d] %s (%s)",
                    task_id[:8], i, selected.alias, selected.account_id[:8],
                )
        return results

    def release_multiple_accounts(self, task_id: str) -> int:
        """
        释放任务组的所有合成分配（匹配 {task_id}__w* 前缀）。

        返回：
            int: 成功释放的账号数
        """
        released = 0
        prefix = f"{task_id}__w"
        with self._lock:
            sub_keys = [k for k in self._assignments if k.startswith(prefix)]
            for sub_key in sub_keys:
                assignment = self._assignments[sub_key]
                if not assignment.is_active:
                    continue
                account_id = assignment.account_id
                assignment.released_at = time.time()
                if account_id in self._account_tasks:
                    del self._account_tasks[account_id]
                released += 1
                logger.info(
                    "释放任务组账号 %s (%s)，使用时长 %.1fs",
                    assignment.account_alias, account_id[:8], assignment.duration_sec,
                )
        return released

    def set_strategy(self, strategy: str) -> None:
        """设置分配策略"""
        if strategy not in ("round_robin", "least_used"):
            raise ValueError(f"未知的分配策略: {strategy}")
        with self._lock:
            self._strategy = strategy
            logger.info(f"账号分配策略已切换为: {strategy}")


# 全局单例
_dispatcher: Optional[AccountDispatcher] = None
_dispatcher_lock = threading.Lock()


def get_dispatcher() -> AccountDispatcher:
    """获取全局账号分配器单例"""
    global _dispatcher
    if _dispatcher is None:
        with _dispatcher_lock:
            if _dispatcher is None:
                _dispatcher = AccountDispatcher()
    return _dispatcher
