"""
并发爬取功能测试

测试账号分配、任务绑定、并发执行等功能。
"""
import pytest
import time
from unittest.mock import Mock, patch

from crawler.account_dispatcher import AccountDispatcher, AccountAssignment
from crawler.account_pool import AccountEntry
from api.services import task_manager


class TestAccountDispatcher:
    """账号分配器测试"""

    def setup_method(self):
        """测试前准备"""
        self.dispatcher = AccountDispatcher()

    def test_assign_account_single(self):
        """测试单账号分配"""
        # 创建模拟账号
        account = AccountEntry(
            account_id="acc_1",
            alias="@user1",
            cookies=[{"name": "auth_token", "value": "token1"}],
        )

        with patch("crawler.account_dispatcher.get_pool") as mock_pool:
            mock_pool.return_value.get_all_accounts.return_value = [account]
            mock_pool.return_value.get_account.return_value = account

            # 分配账号
            assigned = self.dispatcher.assign_account("task_1")
            assert assigned is not None
            assert assigned.account_id == "acc_1"
            assert assigned.alias == "@user1"

    def test_assign_account_multiple(self):
        """测试多账号轮询分配"""
        accounts = [
            AccountEntry(
                account_id=f"acc_{i}",
                alias=f"@user{i}",
                cookies=[{"name": "auth_token", "value": f"token{i}"}],
            )
            for i in range(1, 4)
        ]

        with patch("crawler.account_dispatcher.get_pool") as mock_pool:
            mock_pool.return_value.get_all_accounts.return_value = accounts
            mock_pool.return_value.get_account.side_effect = lambda aid: next(
                (a for a in accounts if a.account_id == aid), None
            )

            # 分配三个任务到三个账号
            assigned_1 = self.dispatcher.assign_account("task_1")
            assigned_2 = self.dispatcher.assign_account("task_2")
            assigned_3 = self.dispatcher.assign_account("task_3")

            assert assigned_1.account_id == "acc_1"
            assert assigned_2.account_id == "acc_2"
            assert assigned_3.account_id == "acc_3"

    def test_release_account(self):
        """测试账号释放"""
        account = AccountEntry(
            account_id="acc_1",
            alias="@user1",
            cookies=[{"name": "auth_token", "value": "token1"}],
        )

        with patch("crawler.account_dispatcher.get_pool") as mock_pool:
            mock_pool.return_value.get_all_accounts.return_value = [account]
            mock_pool.return_value.get_account.return_value = account

            # 分配账号
            self.dispatcher.assign_account("task_1")

            # 释放账号
            released = self.dispatcher.release_account("task_1")
            assert released is True

            # 验证账号已释放
            assignment = self.dispatcher.get_assignment("task_1")
            assert assignment.released_at is not None

    def test_account_status(self):
        """测试账号状态查询"""
        accounts = [
            AccountEntry(
                account_id=f"acc_{i}",
                alias=f"@user{i}",
                cookies=[{"name": "auth_token", "value": f"token{i}"}],
            )
            for i in range(1, 3)
        ]

        with patch("crawler.account_dispatcher.get_pool") as mock_pool:
            mock_pool.return_value.get_all_accounts.return_value = accounts
            mock_pool.return_value.get_account.side_effect = lambda aid: next(
                (a for a in accounts if a.account_id == aid), None
            )

            # 分配一个账号
            self.dispatcher.assign_account("task_1")

            # 查询状态
            status = self.dispatcher.get_account_status()
            assert status["total_accounts"] == 2
            assert status["active_assignments"] == 1
            assert len(status["accounts"]) == 2


class TestTaskManagerAccountBinding:
    """任务管理器账号绑定测试"""

    def test_bind_account(self):
        """测试账号绑定"""
        task_id = task_manager.create_task(
            keyword="test",
            product="Top",
            max_count=100,
        )

        # 绑定账号
        result = task_manager.bind_account(task_id, "acc_1", "@user1")
        assert result is True

        # 验证绑定
        acc_id, acc_alias = task_manager.get_task_account(task_id)
        assert acc_id == "acc_1"
        assert acc_alias == "@user1"

    def test_release_account(self):
        """测试账号释放"""
        task_id = task_manager.create_task(
            keyword="test",
            product="Top",
            max_count=100,
        )

        # 绑定账号
        task_manager.bind_account(task_id, "acc_1", "@user1")

        # 释放账号
        result = task_manager.release_account(task_id)
        assert result is True

        # 验证释放
        acc_id, acc_alias = task_manager.get_task_account(task_id)
        assert acc_id is None
        assert acc_alias is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
