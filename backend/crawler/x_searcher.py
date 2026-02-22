"""
X 搜索爬虫核心模块（v3 - 支持可暂停/可中止的回复抓取与 BFS/DFS 策略）

变更：
- 每页检查任务控制信号（pause/stop），可随时暂停或终止
- 页面首次加载后等待 crawler_initial_wait 秒，确保内容渲染完毕
- 翻页间隔引入 ±20% 随机扰动，模拟人工操作降低被反爬概率
"""
import time
import random
import logging
from typing import Literal, Optional
from urllib.parse import quote

from crawler.browser import get_new_tab
from crawler.auth import ensure_login
from crawler.parser import parse_search_response
from crawler.checkpoint import save_checkpoint, load_checkpoint, delete_checkpoint
from crawler.response_saver import save_raw_response
from crawler.page_health import navigate_with_retry, is_error_page
import api.services.task_manager as _task_mgr
from config import settings

logger = logging.getLogger(__name__)

SEARCH_TIMELINE_PATTERN = "SearchTimeline"
SEARCH_URL_TEMPLATE = "https://x.com/search?q={query}&src=typed_query"

ProductType = Literal["Top", "Latest", "Photos", "Videos"]
CrawlStrategy = Literal["bfs", "dfs"]

_TAB_MAP: dict[str, str] = {
    "Top": "",
    "Latest": "&f=live",
    "Photos": "&f=image",
    "Videos": "&f=video",
}


class StopSignal(Exception):
    """爬虫被主动终止时抛出"""
    pass


class SearchResult:
    """搜索结果容器"""

    def __init__(
        self,
        tweets: list[dict],
        total_fetched: int,
        keyword: str,
        resumed: bool = False,
        replies_fetched: int = 0,
        stopped: bool = False,
    ):
        self.tweets = tweets
        self.total_fetched = total_fetched
        self.keyword = keyword
        self.resumed = resumed
        self.replies_fetched = replies_fetched
        self.stopped = stopped


def _jittered_sleep(base_seconds: float) -> None:
    """带随机扰动的等待（±20%），模拟人工操作节奏"""
    jitter = base_seconds * 0.2
    actual = base_seconds + random.uniform(-jitter, jitter)
    time.sleep(max(0.5, actual))


def _check_signal(task_id: Optional[str]) -> None:
    """
    检查任务控制信号：
    - stop  → 抛出 StopSignal 异常，终止爬虫
    - pause → 轮询等待，直到信号变为 run（支持继续）
    - run   → 直接返回（正常）
    """
    if not task_id:
        return
    while True:
        signal = _task_mgr.get_signal(task_id)
        if signal == "stop":
            raise StopSignal(f"任务 {task_id} 收到终止信号")
        elif signal == "pause":
            logger.info(f"任务 {task_id} 已暂停，等待继续信号...")
            time.sleep(1)
        else:
            break


def search(
    keyword: str,
    max_count: int = 20,
    product: ProductType = "Top",
    timeout: Optional[float] = None,
    task_id: Optional[str] = None,
    resume: bool = True,
    fetch_replies: bool = False,
    max_replies_per_tweet: int = 20,
    crawl_strategy: CrawlStrategy = "bfs",
) -> SearchResult:
    """
    搜索 X 推文（含断点续爬 + 可选回复抓取 + 可暂停/可终止）

    Args:
        keyword:               搜索关键词
        max_count:             最多获取的推文数量
        product:               搜索类型
        timeout:               等待每个数据包的超时（秒）
        task_id:               任务 ID（用于检查点文件命名和原始响应存储）
        resume:                是否尝试从已有检查点继续（True = 断点续爬）
        fetch_replies:         是否抓取每条推文的回复
        max_replies_per_tweet: 每条推文最多抓取的回复数量
        crawl_strategy:        "bfs"（广度优先）或 "dfs"（深度优先）

    Returns:
        SearchResult 对象
    """
    if timeout is None:
        timeout = settings.crawler_timeout

    # ── 1. 尝试加载检查点 ───────────────────────────────────────────
    all_tweets: list[dict] = []
    seen_ids: set[str] = set()
    start_cursor: Optional[str] = None
    page_fetched: int = 0
    resumed = False

    if resume and task_id:
        ckpt = load_checkpoint(task_id)
        if ckpt and ckpt.get("keyword") == keyword and ckpt.get("product") == product:
            all_tweets = ckpt.get("tweets", [])
            seen_ids = {t["id"] for t in all_tweets if t.get("id")}
            start_cursor = ckpt.get("next_cursor")
            page_fetched = ckpt.get("page_fetched", 0)
            resumed = True
            logger.info(
                f"从断点恢复：task_id={task_id}，"
                f"已有 {len(all_tweets)} 条，cursor={'有' if start_cursor else '无'}"
            )
            if len(all_tweets) >= max_count or not start_cursor:
                # 断点恢复时若搜索已完成，直接进入回复抓取阶段
                if fetch_replies and not _tweets_have_replies(all_tweets):
                    all_tweets = _fetch_replies_for_tweets(
                        all_tweets, max_replies_per_tweet, task_id, timeout, crawl_strategy
                    )
                return SearchResult(
                    tweets=all_tweets[:max_count],
                    total_fetched=len(all_tweets[:max_count]),
                    keyword=keyword,
                    resumed=resumed,
                    replies_fetched=_count_replies(all_tweets),
                )

    # ── 2. 启动浏览器标签页 ─────────────────────────────────────────
    tab = get_new_tab()
    try:
        if not ensure_login(tab):
            raise RuntimeError(
                "未检测到 X 登录状态。"
                "请先在浏览器中登录 X 账号，"
                "程序会自动检测已登录的 Chrome 用户数据目录。"
            )

        search_url = _build_search_url(keyword, product)
        logger.info(
            f"开始搜索: keyword='{keyword}', product={product}, "
            f"max_count={max_count}, strategy={crawl_strategy}, "
            f"fetch_replies={fetch_replies}, 从断点={resumed}"
        )

        # ── 3. 开启监听 ─────────────────────────────────────────────
        tab.listen.start(SEARCH_TIMELINE_PATTERN)

        # ── 4. 访问搜索页面（含错误页自动刷新）───────────────────────────
        ok = navigate_with_retry(
            tab,
            search_url,
            max_retries=3,
            base_wait=3.0,
            load_timeout=30.0,
            post_load_wait=settings.crawler_initial_wait,
            task_id=task_id,
        )
        if not ok:
            raise RuntimeError(f"搜索页面反复出现错误，无法加载: {search_url}")

        page_num = page_fetched + 1

        while len(all_tweets) < max_count:
            # 每页开始前检查控制信号
            _check_signal(task_id)

            logger.info(f"等待第 {page_num} 页数据包（timeout={timeout}s）...")
            if task_id:
                _task_mgr.update_task_phase(task_id, f"等待第 {page_num} 页数据包...")
            packet = tab.listen.wait(timeout=timeout, raise_err=False)
            if not packet:
                # 超时时先检测是否出现了错误页
                if is_error_page(tab):
                    logger.warning(f"第 {page_num} 页：检测到 X 错误页面，尝试刷新重试...")
                    tab.listen.stop()
                    ok = navigate_with_retry(
                        tab, tab.url,
                        max_retries=2, base_wait=3.0,
                        post_load_wait=settings.crawler_initial_wait,
                        task_id=task_id,
                    )
                    tab.listen.start(SEARCH_TIMELINE_PATTERN)
                    if ok:
                        logger.info(f"第 {page_num} 页：刷新成功，继续等待数据包")
                        continue  # 重新等待数据包
                logger.warning(f"第 {page_num} 页等待超时，停止爬取")
                break

            try:
                body = packet.response.body
                if not isinstance(body, dict):
                    logger.debug(f"非 JSON 响应，跳过（url={packet.url[:80]}）")
                    continue

                # 保存原始搜索响应
                if task_id:
                    save_raw_response(task_id, page_num, body)

                tweets_page, bottom_cursor, _ = parse_search_response(body)

                # 去重
                new_tweets = [t for t in tweets_page if t.get("id") not in seen_ids]
                for t in new_tweets:
                    seen_ids.add(t.get("id", ""))

                # ── DFS：每批新推文立即抓取回复 ────────────────────
                if fetch_replies and crawl_strategy == "dfs" and new_tweets:
                    logger.info(f"[DFS] 立即抓取 {len(new_tweets)} 条新推文的回复...")

                    # ★ 关键修复：进入回复抓取前，先把已搜到的推文推入预览
                    # 让前端可以立即看到搜索结果，不必等回复全部抓完
                    _tmp_all = list(all_tweets) + new_tweets
                    if task_id:
                        _task_mgr.update_task_progress(task_id, page_num, _tmp_all)
                        _task_mgr.update_task_phase(
                            task_id,
                            f"第 {page_num} 页已解析 {len(new_tweets)} 条，正在抓取回复..."
                        )

                    # 停止搜索监听，切换到回复抓取，完成后重新开启搜索监听
                    tab.listen.stop()

                    def _on_reply_progress(tweet_id: str, replies: list[dict]):
                        """每条推文回复抓取完成后更新整体进度"""
                        if task_id:
                            _task_mgr.update_task_replies_progress(task_id, tweet_id, len(replies))

                    new_tweets = _fetch_replies_for_tweets_with_tab(
                        new_tweets, max_replies_per_tweet, task_id, timeout,
                        progress_callback=_on_reply_progress,
                    )
                    tab.listen.start(SEARCH_TIMELINE_PATTERN)

                all_tweets.extend(new_tweets)

                logger.info(
                    f"第 {page_num} 页：{len(tweets_page)} 条（新增 {len(new_tweets)} 条），"
                    f"累计 {len(all_tweets)} 条"
                )

                # 写检查点（每页立即保存）
                if task_id:
                    save_checkpoint(
                        task_id=task_id,
                        keyword=keyword,
                        product=product,
                        tweets_so_far=all_tweets,
                        next_cursor=bottom_cursor,
                        page_fetched=page_num,
                    )
                    _task_mgr.update_task_progress(task_id, page_num, list(all_tweets))
                    _task_mgr.update_task_phase(task_id, f"已完成第 {page_num} 页，共 {len(all_tweets)} 条")

                if not bottom_cursor:
                    logger.info("无更多数据（bottom_cursor 为空），停止")
                    break
                if len(all_tweets) >= max_count:
                    logger.info(f"已达目标 {max_count} 条，停止")
                    break

            except StopSignal:
                raise
            except Exception as e:
                logger.error(f"第 {page_num} 页解析失败: {e}", exc_info=True)
                break

            # 滚动翻页（带随机扰动的间隔）
            page_num += 1
            _jittered_sleep(settings.crawler_page_interval)
            tab.scroll.to_bottom()

    finally:
        try:
            tab.listen.stop()
            tab.close()
        except Exception:
            pass

    all_tweets = all_tweets[:max_count]

    # ── BFS：搜索完成后统一抓取所有推文的回复 ──────────────────────
    if fetch_replies and crawl_strategy == "bfs":
        logger.info(f"[BFS] 搜索完成，开始统一抓取 {len(all_tweets)} 条推文的回复...")
        all_tweets = _fetch_replies_for_tweets(
            all_tweets, max_replies_per_tweet, task_id, timeout, crawl_strategy
        )
        # 更新最终进度
        if task_id:
            _task_mgr.update_task_progress(task_id, page_num, list(all_tweets))

    # 爬取完成，删除检查点
    if task_id and len(all_tweets) >= max_count:
        delete_checkpoint(task_id)

    result = SearchResult(
        tweets=all_tweets,
        total_fetched=len(all_tweets),
        keyword=keyword,
        resumed=resumed,
        replies_fetched=_count_replies(all_tweets),
    )
    logger.info(
        f"搜索完成：{result.total_fetched} 条推文，"
        f"回复 {result.replies_fetched} 条，resumed={resumed}"
    )
    return result


# ═══════════════════════════════════════════════════════════════════
#  回复抓取辅助
# ═══════════════════════════════════════════════════════════════════

def _fetch_replies_for_tweets(
    tweets: list[dict],
    max_replies_per_tweet: int,
    task_id: Optional[str],
    timeout: Optional[float],
    strategy: str,
) -> list[dict]:
    """BFS 模式批量抓取回复（延迟导入防止循环引用）"""
    from crawler.reply_fetcher import fetch_replies_batch

    def on_progress(tweet_id: str, replies: list[dict]):
        if task_id:
            _task_mgr.update_task_replies_progress(task_id, tweet_id, len(replies))

    return fetch_replies_batch(
        tweets=tweets,
        max_replies_per_tweet=max_replies_per_tweet,
        task_id=task_id,
        timeout=timeout,
        progress_callback=on_progress,
    )


def _fetch_replies_for_tweets_with_tab(
    tweets: list[dict],
    max_replies_per_tweet: int,
    task_id: Optional[str],
    timeout: Optional[float],
    progress_callback=None,
) -> list[dict]:
    """DFS 模式：在当前进程内顺序抓取回复（每条推文单独新开标签页）"""
    from crawler.reply_fetcher import fetch_replies

    updated = []
    total = len(tweets)
    for idx, tweet in enumerate(tweets):
        # 检查停止信号
        _check_signal(task_id)

        tweet_id = tweet.get("id", "")
        screen_name = (tweet.get("author") or {}).get("screen_name", "")
        if not tweet_id or not screen_name:
            tweet = dict(tweet)
            tweet["replies"] = []
            updated.append(tweet)
            continue

        # 更新阶段提示（告知用户正在抓第几条推文的回复）
        if task_id:
            _task_mgr.update_task_phase(
                task_id,
                f"正在抓取第 {idx + 1}/{total} 条推文的回复 (@{screen_name})..."
            )

        try:
            replies = fetch_replies(
                tweet_id=tweet_id,
                screen_name=screen_name,
                max_count=max_replies_per_tweet,
                task_id=task_id,
                timeout=timeout,
            )
            tweet = dict(tweet)
            tweet["replies"] = replies
        except StopSignal:
            raise
        except Exception as e:
            logger.error(f"[DFS] 抓取 tweet_id={tweet_id} 回复失败: {e}", exc_info=True)
            tweet = dict(tweet)
            tweet["replies"] = []
        updated.append(tweet)

        # 每条回复抓完后触发回调（更新 replies_fetched 计数）
        if progress_callback:
            progress_callback(tweet_id, tweet.get("replies", []))

        _jittered_sleep(settings.crawler_page_interval)
    return updated


def _tweets_have_replies(tweets: list[dict]) -> bool:
    """检查推文列表中是否已有回复数据（断点恢复时用于判断是否需要重新抓取回复）"""
    return any("replies" in tweet and tweet["replies"] for tweet in tweets)


def _count_replies(tweets: list[dict]) -> int:
    """统计推文列表中回复总数"""
    return sum(len(tweet.get("replies", [])) for tweet in tweets)


# ═══════════════════════════════════════════════════════════════════
#  URL 构建
# ═══════════════════════════════════════════════════════════════════

def _build_search_url(keyword: str, product: ProductType) -> str:
    """构建搜索 URL"""
    return SEARCH_URL_TEMPLATE.format(query=quote(keyword)) + _TAB_MAP.get(product, "")
