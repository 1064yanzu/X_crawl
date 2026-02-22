"""
爬虫服务层（v3 - 支持回复抓取、BFS/DFS 策略、任务主动终止）
"""
import logging
from api.services import task_manager
from crawler.x_searcher import search, StopSignal

logger = logging.getLogger(__name__)


def run_search_task(
    task_id: str,
    keyword: str,
    max_count: int,
    product: str,
    resume: bool = True,
    fetch_replies: bool = False,
    max_replies_per_tweet: int = 20,
    crawl_strategy: str = "bfs",
) -> None:
    """
    执行搜索任务（BackgroundTasks 后台运行）
    - 自动透传 task_id 给爬虫，实现断点续爬
    - 支持回复抓取（BFS/DFS 策略）
    - 解析结果直接以 dict 存储
    - 捕获 StopSignal，将任务状态设为 stopped（区别于 failed）
    """
    task_manager.update_task_status(task_id, "running")
    logger.info(
        f"任务开始: task_id={task_id}, keyword='{keyword}', "
        f"strategy={crawl_strategy}, fetch_replies={fetch_replies}, resume={resume}"
    )

    try:
        result = search(
            keyword=keyword,
            max_count=max_count,
            product=product,
            task_id=task_id,
            resume=resume,
            fetch_replies=fetch_replies,
            max_replies_per_tweet=max_replies_per_tweet,
            crawl_strategy=crawl_strategy,
        )
        task_manager.update_task_result(
            task_id=task_id,
            tweets=result.tweets,
            resumed=result.resumed,
            replies_fetched=result.replies_fetched,
        )
        logger.info(
            f"任务完成: task_id={task_id}, "
            f"推文 {len(result.tweets)} 条, 回复 {result.replies_fetched} 条, "
            f"resumed={result.resumed}"
        )
    except StopSignal as e:
        # 用户主动终止，保存已抓取的数据
        task_data = task_manager.get_task(task_id) or {}
        tweets_so_far = task_data.get("tweets", [])
        task_manager.update_task_stopped(task_id, tweets_so_far)
        logger.info(f"任务主动终止: task_id={task_id}, 已保存 {len(tweets_so_far)} 条数据, reason={e}")
    except Exception as e:
        error_msg = str(e)
        task_manager.update_task_error(task_id, error_msg)
        logger.error(f"任务失败: task_id={task_id}, error={error_msg}", exc_info=True)
