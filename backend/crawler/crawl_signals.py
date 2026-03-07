"""爬虫通用信号定义，避免模块间循环依赖。"""
from typing import Literal

RiskState = Literal["none", "challenge", "rate_limited", "login_required"]


class StopSignal(Exception):
    """任务被主动停止时抛出，可携带已处理部分数据。"""

    def __init__(self, message: str = "", partial_tweets: list[dict] | None = None):
        super().__init__(message)
        self.partial_tweets = partial_tweets or []


class ChallengeSignal(Exception):
    """检测到风控挑战并达到重试上限时抛出。"""

    def __init__(self, message: str, risk_state: RiskState = "challenge"):
        super().__init__(message)
        self.risk_state = risk_state


class LoginRequiredPause(Exception):
    """检测到登录态失效且无法自动恢复时抛出，用于让任务进入暂停态。"""

    def __init__(
        self,
        message: str,
        *,
        reason: str = "login_required",
        session_mode: str = "unknown",
        effective_user_data_path: str | None = None,
    ):
        super().__init__(message)
        self.risk_state: RiskState = "login_required"
        self.reason = reason
        self.session_mode = session_mode
        self.effective_user_data_path = effective_user_data_path
