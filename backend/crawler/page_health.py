"""
页面健康检测工具

检测 X/Twitter 常见错误页面并自动刷新重试：
- "Something went wrong" 通用错误页
- 空白页 / 未加载完成

使用 DrissionPage 的页面文字检测，无需依赖特定 DOM 结构。
"""
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# X 错误页面的特征文字（多语言兜底）
_ERROR_MARKERS = [
    "something went wrong",
    "try reloading",
    "something went wrong, but don",  # 英文
    "出错了",                           # 中文
    "try again",
    "hmm, this page doesn",            # 404 类错误
]


def is_error_page(tab) -> bool:
    """
    检测当前页面是否为 X 错误页面。

    原理：获取页面纯文字内容，判断是否含有错误特征词。
    避免用 CSS 选择器依赖 DOM 结构（X 会频繁改版）。
    """
    try:
        text = tab.html or ""
        text_lower = text.lower()
        for marker in _ERROR_MARKERS:
            if marker in text_lower:
                return True
        return False
    except Exception:
        return False


def navigate_with_retry(
    tab,
    url: str,
    *,
    max_retries: int = 3,
    base_wait: float = 3.0,
    load_timeout: float = 30.0,
    post_load_wait: float = 0.0,
    task_id: Optional[str] = None,
) -> bool:
    """
    导航到目标 URL，遇到错误页面自动刷新重试。

    Args:
        tab:            DrissionPage 标签页对象
        url:            目标 URL
        max_retries:    最大重试次数（不含首次）
        base_wait:      每次重试前的等待时间（秒），每次翻倍
        load_timeout:   页面加载超时（秒）
        post_load_wait: 加载成功后额外等待时间（秒，0 表示不额外等待）
        task_id:        任务 ID（仅用于日志标记）

    Returns:
        True  = 页面加载正常
        False = 所有重试失败
    """
    log_prefix = f"[task={task_id}] " if task_id else ""

    for attempt in range(max_retries + 1):
        try:
            if attempt == 0:
                tab.get(url, timeout=load_timeout)
            else:
                wait = base_wait * (2 ** (attempt - 1))
                logger.warning(
                    f"{log_prefix}检测到错误页面，{wait:.1f}s 后第 {attempt} 次刷新重试... (url={url[:80]})"
                )
                time.sleep(wait)
                tab.refresh()
                # 等待刷新后页面加载
                time.sleep(2.0)

            if is_error_page(tab):
                if attempt == max_retries:
                    logger.error(f"{log_prefix}已达最大重试次数 {max_retries}，放弃 (url={url[:80]})")
                    return False
                continue  # 继续重试

            # 页面正常
            if post_load_wait > 0:
                time.sleep(post_load_wait)

            if attempt > 0:
                logger.info(f"{log_prefix}第 {attempt} 次刷新后页面恢复正常")

            return True

        except Exception as e:
            if attempt == max_retries:
                logger.error(f"{log_prefix}导航失败，已达最大重试次数: {e}")
                return False
            logger.warning(f"{log_prefix}导航异常 (attempt={attempt}): {e}")
            time.sleep(base_wait)

    return False
