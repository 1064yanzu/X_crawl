"""
人性化鼠标行为模块

提供三阶贝塞尔曲线平滑鼠标移动，防止机器人式跳变。
适用于百万级数据爬取的长时间运行场景。
"""
import time
import math
import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def move_mouse_smoothly(
    tab,
    tx: int,
    ty: int,
    *,
    start_x: int,
    start_y: int,
    task_id: Optional[str] = None,
) -> None:
    """三阶贝塞尔曲线平滑鼠标移动（含高斯手部抖动）"""
    dx = tx - start_x
    dy = ty - start_y
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 1:
        return
    steps = max(8, min(25, int(dist / 20)))

    # 控制点：让曲线自然弯曲
    cp1x = start_x + dx * 0.25 + random.gauss(0, max(1.0, abs(dy) * 0.15))
    cp1y = start_y + dy * 0.25 + random.gauss(0, max(1.0, abs(dx) * 0.15))
    cp2x = start_x + dx * 0.75 + random.gauss(0, max(1.0, abs(dy) * 0.15))
    cp2y = start_y + dy * 0.75 + random.gauss(0, max(1.0, abs(dx) * 0.15))

    for i in range(steps + 1):
        t = i / steps
        # 三阶贝塞尔
        x = ((1-t)**3 * start_x + 3*(1-t)**2*t * cp1x
             + 3*(1-t)*t**2 * cp2x + t**3 * tx)
        y = ((1-t)**3 * start_y + 3*(1-t)**2*t * cp1y
             + 3*(1-t)*t**2 * cp2y + t**3 * ty)
        # 高斯手部抖动
        x += random.gauss(0, 0.8)
        y += random.gauss(0, 0.8)

        try:
            tab.actions.move_to((int(x), int(y)))
        except Exception:
            try:
                tab.run_js(
                    f"document.dispatchEvent(new MouseEvent('mousemove', "
                    f"{{clientX:{int(x)}, clientY:{int(y)}, bubbles:true}}))"
                )
            except Exception:
                pass

        # ease-in-out 缓动：中间步最快，两端最慢
        mid_factor = 1 - abs(2 * t - 1)  # 0 at edges, 1 in middle
        delay = 0.003 + (0.017 - 0.003) * (1 - mid_factor)
        time.sleep(delay)


def random_mouse_wander(
    tab,
    *,
    moves: int = 2,
    task_id: Optional[str] = None,
) -> None:
    """在视口内随机移动鼠标，模拟真人偶尔挪动鼠标"""
    from crawler.utils import interruptible_sleep
    try:
        dims = tab.run_js("return [window.innerWidth, window.innerHeight]")
        if not dims or len(dims) < 2:
            return
        w, h = int(dims[0]), int(dims[1])
        last_x, last_y = w // 2, h // 2
        for _ in range(moves):
            tx = random.randint(50, w - 50)
            ty = random.randint(50, h - 50)
            try:
                move_mouse_smoothly(tab, tx, ty, start_x=last_x, start_y=last_y, task_id=task_id)
                last_x, last_y = tx, ty
            except Exception:
                pass
            interruptible_sleep(random.uniform(0.1, 0.4), task_id=task_id)
    except Exception as e:
        logger.debug(f"random_mouse_wander 失败（忽略）: {e}")


def natural_click(tab, element, *, task_id: Optional[str] = None) -> None:
    """自然点击：先移动鼠标到元素，停顿后点击"""
    from crawler.utils import interruptible_sleep
    try:
        try:
            loc = element.rect
            tx = int(loc.get('x', 0) + loc.get('width', 0) / 2)
            ty = int(loc.get('y', 0) + loc.get('height', 0) / 2)
            move_mouse_smoothly(tab, tx, ty, start_x=tx - 100, start_y=ty - 50, task_id=task_id)
            interruptible_sleep(random.uniform(0.05, 0.15), task_id=task_id)
            tab.actions.click()
        except Exception:
            element.click()
    except Exception as e:
        logger.debug(f"natural_click 失败（忽略）: {e}")
