"""
爬虫服务层（升级版）
适配完整字段的 parser，支持断点续爬参数传递
"""
import logging
from api.services import task_manager
from crawler.x_searcher import search

logger = logging.getLogger(__name__)


def run_search_task(
    task_id: str,
    keyword: str,
    max_count: int,
    product: str,
    resume: bool = True,
) -> None:
    """
    执行搜索任务（BackgroundTasks 后台运行）
    - 自动透传 task_id 给爬虫，实现断点续爬
    - 解析结果直接以 dict 存储（兼容 Pydantic 序列化）
    """
    task_manager.update_task_status(task_id, "running")
    logger.info(f"任务开始: task_id={task_id}, keyword='{keyword}', resume={resume}")

    try:
        result = search(
            keyword=keyword,
            max_count=max_count,
            product=product,
            task_id=task_id,
            resume=resume,
        )
        task_manager.update_task_result(task_id, result.tweets, resumed=result.resumed)
        logger.info(f"任务完成: task_id={task_id}, 共 {len(result.tweets)} 条，resumed={result.resumed}")
    except Exception as e:
        error_msg = str(e)
        task_manager.update_task_error(task_id, error_msg)
        logger.error(f"任务失败: task_id={task_id}, error={error_msg}", exc_info=True)
