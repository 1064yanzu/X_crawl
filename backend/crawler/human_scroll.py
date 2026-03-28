"""
人性化滚动模块

模拟真人浏览行为的多种滚动模式：

1. human_like_scroll()   — 翻页时的渐进式滚动（触发 API 懒加载）
2. simulate_reading()    — 获取推文后模拟阅读浏览（慢速、几乎不停）
3. idle_scroll()         — DFS 抓评论期间搜索页的轻微滚动（保持活跃感）

设计原则：
  - 速度偏慢（真人不是机器人，不会飞速翻页）
  - 帖子页面更慢（每条帖子都值得"看一看"）
  - 偶尔有随机停顿（假装在读某条帖子）
  - 偶尔回滚（假装回看感兴趣的内容）
  - Referer 头由浏览器自动管理（无需手动设置）
"""
import random
import logging
from typing import Optional

from crawler.utils import interruptible_sleep, lognormal_sleep
from crawler.scroll_safe import safe_scroll_down, safe_scroll_up, safe_scroll_to_bottom
from crawler.mouse_behavior import random_mouse_wander

logger = logging.getLogger(__name__)


def human_like_scroll(
    tab,
    *,
    task_id: Optional[str] = None,
    min_step_px: int = 150,
    max_step_px: int = 350,
    min_pause: float = 0.6,
    max_pause: float = 1.5,
    steps: int = 0,
    scroll_back_chance: float = 0.10,
    scroll_back_px_range: tuple[int, int] = (50, 150),
    finish_at_bottom: bool = False,
) -> None:
    """
    翻页滚动：模拟真人慢慢往下滑、触发 API 加载新数据。

    比直接 scroll_to_bottom() 自然得多：小步滑动、随机停顿、偶尔回看。

    Args:
        tab:                DrissionPage 标签页
        task_id:            任务 ID（用于中断响应）
        min_step_px:        每步最小滚动像素（默认 150，较慢）
        max_step_px:        每步最大滚动像素（默认 350）
        min_pause:          步间最小停顿（秒）
        max_pause:          步间最大停顿（秒）
        steps:              滚动步数（0 = 自动 4~7 步）
        scroll_back_chance: 随机回滚概率
        scroll_back_px_range: 回滚像素范围
        finish_at_bottom:   最后是否滚到底部确保触发懒加载
    """
    if steps <= 0:
        steps = random.randint(2, 4)

    for i in range(steps):
        px = random.randint(min_step_px, max_step_px)
        safe_scroll_down(tab, px, task_id=task_id)

        # 大部分时候短停顿，偶尔长停顿（假装在看某条帖子）
        if random.random() < 0.06:
            pause = random.uniform(0.8, 1.5)  # 6% 概率长停顿
        else:
            pause = random.uniform(min_pause, min(max_pause, 1.0))
        interruptible_sleep(pause, task_id=task_id)

        # 偶尔回滚（非最后一步）
        if i < steps - 1 and random.random() < scroll_back_chance:
            back_px = random.randint(*scroll_back_px_range)
            safe_scroll_up(tab, back_px, task_id=task_id)
            interruptible_sleep(random.uniform(0.3, 0.6), task_id=task_id)

    if finish_at_bottom:
        safe_scroll_to_bottom(tab, task_id=task_id)


def simulate_reading(
    tab,
    *,
    task_id: Optional[str] = None,
    tweet_count: int = 0,
) -> None:
    """
    模拟人类阅读搜索结果：收到一批推文后，快速扫过。

    轻量版：步数收敛，保持随机特征即可，避免占用过多时间。

    Args:
        tab:           DrissionPage 标签页
        task_id:       任务 ID
        tweet_count:   本批获取的推文数量（影响阅读时长）
    """
    # 根据推文数量决定阅读步数（限制上限防止过慢）
    if tweet_count <= 0:
        steps = random.randint(2, 3)
    else:
        # 20 条→4~6 步；5 条→2~3 步
        steps = max(2, min(6, tweet_count // 4 + random.randint(1, 2)))

    for i in range(steps):
        # 小幅滚动（一条推文大约 200~400px 高）
        px = random.randint(150, 350)
        safe_scroll_down(tab, px, task_id=task_id)

        # 阅读节奏：大部分快速扫过，偶尔停一下
        roll = random.random()
        if roll < 0.08:
            # 8% 概率长驻留
            lognormal_sleep(1.5, sigma=0.35, floor=0.8, ceiling=3.0, task_id=task_id)
        elif roll < 0.30:
            # 22% 概率中等停留
            lognormal_sleep(0.8, sigma=0.3, floor=0.4, ceiling=1.8, task_id=task_id)
        else:
            # 70% 快速扫过
            lognormal_sleep(0.4, sigma=0.3, floor=0.15, ceiling=1.0, task_id=task_id)

        # 偶尔回滚（回看感兴趣的帖子）
        if random.random() < 0.08:
            back_px = random.randint(60, 160)
            safe_scroll_up(tab, back_px, task_id=task_id)
            lognormal_sleep(0.4, sigma=0.25, floor=0.15, ceiling=1.0, task_id=task_id)


def idle_scroll(
    tab,
    *,
    task_id: Optional[str] = None,
) -> None:
    """
    空闲微滚动：DFS 抓评论期间搜索页的轻微活动。

    当其他标签页在抓取深度评论时，搜索页不应完全静止不动。
    真人会偶尔回到搜索页滑一下、看看还有什么帖子。
    这个函数做 1~2 次小幅滚动，耗时很短（~1s），不会干扰评论抓取。

    Args:
        tab:       搜索页标签页
        task_id:   任务 ID
    """
    try:
        # 做 1~2 次微幅滚动
        micro_steps = random.randint(1, 2)

        if random.random() < 0.40:
            random_mouse_wander(tab, moves=1, task_id=task_id)

        for _ in range(micro_steps):
            px = random.randint(60, 180)
            safe_scroll_down(tab, px, task_id=task_id)
            interruptible_sleep(random.uniform(0.3, 0.6), task_id=task_id)

        # 偶尔回滚一点（20% 概率）
        if random.random() < 0.20:
            safe_scroll_up(tab, random.randint(40, 100), task_id=task_id)
            interruptible_sleep(random.uniform(0.2, 0.4), task_id=task_id)
    except Exception:
        # 任何异常都不应影响主流程
        pass
