"""
人性化滚动模块（效率优化版）

多种滚动模式：

1. human_like_scroll()   — 翻页时的快速滚动（触发 API 懒加载）
2. simulate_reading()    — 获取推文后极快速扫过（几乎不耗时）
3. idle_scroll()         — DFS 抓评论期间搜索页的微滚动（极轻量）

设计原则（效率优先）：
  - 快速翻页（每页翻页耗时 <1.5s）
  - 默认滚到底部确保触发 API 加载
  - 极少概率的微随机（仅保留最低限度的反检测特征）
  - 模拟阅读几乎不耗时（1~2 步极快扫过）
"""
import random
import logging
from typing import Optional

from crawler.utils import interruptible_sleep, lognormal_sleep
from crawler.scroll_safe import safe_scroll_down, safe_scroll_up, safe_scroll_to_bottom

logger = logging.getLogger(__name__)


def human_like_scroll(
    tab,
    *,
    task_id: Optional[str] = None,
    min_step_px: int = 300,
    max_step_px: int = 600,
    min_pause: float = 0.08,
    max_pause: float = 0.25,
    steps: int = 0,
    scroll_back_chance: float = 0.03,
    scroll_back_px_range: tuple[int, int] = (50, 120),
    finish_at_bottom: bool = True,
) -> None:
    """
    翻页滚动：快速高效地触发 API 懒加载新数据。

    优化后的参数：步幅更大、停顿更短、默认滚到底确保触发加载。

    Args:
        tab:                DrissionPage 标签页
        task_id:            任务 ID（用于中断响应）
        min_step_px:        每步最小滚动像素（优化后 300）
        max_step_px:        每步最大滚动像素（优化后 600）
        min_pause:          步间最小停顿（秒，优化后 0.08）
        max_pause:          步间最大停顿（秒，优化后 0.25）
        steps:              滚动步数（0 = 自动 1~2 步）
        scroll_back_chance: 随机回滚概率（优化后 3%）
        scroll_back_px_range: 回滚像素范围
        finish_at_bottom:   最后是否滚到底部确保触发懒加载（默认开启）
    """
    if steps <= 0:
        steps = random.randint(1, 2)

    for i in range(steps):
        px = random.randint(min_step_px, max_step_px)
        safe_scroll_down(tab, px, task_id=task_id)

        # 短停顿为主，极少长停顿
        if random.random() < 0.03:
            pause = random.uniform(0.2, 0.5)  # 3% 概率稍长停顿
        else:
            pause = random.uniform(min_pause, max_pause)
        interruptible_sleep(pause, task_id=task_id)

        # 偶尔回滚（非最后一步，概率很低）
        if i < steps - 1 and random.random() < scroll_back_chance:
            back_px = random.randint(*scroll_back_px_range)
            safe_scroll_up(tab, back_px, task_id=task_id)
            interruptible_sleep(random.uniform(0.1, 0.3), task_id=task_id)

    if finish_at_bottom:
        safe_scroll_to_bottom(tab, task_id=task_id)


def simulate_reading(
    tab,
    *,
    task_id: Optional[str] = None,
    tweet_count: int = 0,
) -> None:
    """
    模拟人类阅读搜索结果：收到一批推文后，极快速扫过。

    极简版：仅 1~2 步快速扫过，不浪费时间，搜索翻页本身就是最好的模拟。

    Args:
        tab:           DrissionPage 标签页
        task_id:       任务 ID
        tweet_count:   本批获取的推文数量（影响阅读时长）
    """
    # 固定 1~2 步极快扫过
    steps = random.randint(1, 2)

    for i in range(steps):
        px = random.randint(200, 400)
        safe_scroll_down(tab, px, task_id=task_id)

        # 极短停顿
        lognormal_sleep(0.2, sigma=0.25, floor=0.08, ceiling=0.5, task_id=task_id)


def idle_scroll(
    tab,
    *,
    task_id: Optional[str] = None,
) -> None:
    """
    空闲微滚动：DFS 抓评论期间搜索页的轻微活动。

    极简版：单次小幅滚动，耗时极短（<0.5s），不干扰主流程。

    Args:
        tab:       搜索页标签页
        task_id:   任务 ID
    """
    try:
        px = random.randint(80, 200)
        safe_scroll_down(tab, px, task_id=task_id)
        interruptible_sleep(random.uniform(0.1, 0.25), task_id=task_id)
    except Exception:
        # 任何异常都不应影响主流程
        pass
