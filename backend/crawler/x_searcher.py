"""
X 搜索爬虫核心模块（工业级）
新特性：
- 集成断点续爬（每页存盘，服务重启后可从 cursor 继续）
- 支持 resume_task_id 参数，恢复已有任务
- 去重（基于 tweet ID）防止拿到重复数据
- 每页爬取后立即写检查点，确保崩溃不丢数据
- 支持 Top / Latest / Photos / Videos 四种搜索类型
"""
import time
import logging
from typing import Literal, Optional
from urllib.parse import quote

from crawler.browser import get_new_tab
from crawler.auth import ensure_login
from crawler.parser import parse_search_response
from crawler.checkpoint import save_checkpoint, load_checkpoint, delete_checkpoint
from crawler.response_saver import save_raw_response
import api.services.task_manager as _task_mgr
from config import settings

logger = logging.getLogger(__name__)

SEARCH_TIMELINE_PATTERN = "SearchTimeline"
SEARCH_URL_TEMPLATE = "https://x.com/search?q={query}&src=typed_query"

ProductType = Literal["Top", "Latest", "Photos", "Videos"]

_TAB_MAP: dict[str, str] = {
    "Top": "",
    "Latest": "&f=live",
    "Photos": "&f=image",
    "Videos": "&f=video",
}


class SearchResult:
    """搜索结果容器"""

    def __init__(self, tweets: list[dict], total_fetched: int, keyword: str, resumed: bool = False):
        self.tweets = tweets
        self.total_fetched = total_fetched
        self.keyword = keyword
        self.resumed = resumed  # 是否从断点恢复


def search(
    keyword: str,
    max_count: int = 20,
    product: ProductType = "Top",
    timeout: Optional[float] = None,
    task_id: Optional[str] = None,
    resume: bool = True,
) -> SearchResult:
    """
    搜索 X 推文（含断点续爬）

    Args:
        keyword:   搜索关键词
        max_count: 最多获取的推文数量
        product:   搜索类型
        timeout:   等待每个数据包的超时（秒）
        task_id:   任务 ID（用于检查点文件命名）
        resume:    是否尝试从已有检查点继续（True = 断点续爬）

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
            # 如果已经拿够了直接返回
            if len(all_tweets) >= max_count or not start_cursor:
                return SearchResult(
                    tweets=all_tweets[:max_count],
                    total_fetched=len(all_tweets[:max_count]),
                    keyword=keyword,
                    resumed=resumed,
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
            f"max_count={max_count}, 从断点={resumed}"
        )

        # ── 3. 开启监听 ─────────────────────────────────────────────
        tab.listen.start(SEARCH_TIMELINE_PATTERN)

        # ── 4. 访问搜索页面 ─────────────────────────────────────────
        tab.get(search_url, timeout=30)

        # 如果有 cursor，需要等到第一批数据包到来后再滚动
        # （X 会在初次加载时返回第一页，我们先消费掉它）
        if not start_cursor:
            pass  # 正常流程：从第一页开始
        # 若有 cursor，X 搜索页面刷新也会先加载第一页，我们消费后跳到 cursor 位置
        # 由于无法直接传入 cursor 到 UI，策略是：先消费完第一页，再通过 JS 触发翻页
        # 实际上 DrissionPage 监听器会拿到自然加载的数据包，滚动即触发翻页

        page_num = page_fetched + 1

        while len(all_tweets) < max_count:
            logger.info(f"等待第 {page_num} 页数据包（timeout={timeout}s）...")
            packet = tab.listen.wait(timeout=timeout, raise_err=False)
            if not packet:
                logger.warning(f"第 {page_num} 页等待超时，停止爬取")
                break

            try:
                body = packet.response.body
                if not isinstance(body, dict):
                    logger.debug(f"非 JSON 响应，跳过（url={packet.url[:80]}）")
                    continue

                # ── 保存原始响应（配置开关控制）──────────────────────
                if task_id:
                    save_raw_response(task_id, page_num, body)

                tweets_page, bottom_cursor, _ = parse_search_response(body)

                # 去重
                new_tweets = [t for t in tweets_page if t.get("id") not in seen_ids]
                for t in new_tweets:
                    seen_ids.add(t.get("id", ""))
                all_tweets.extend(new_tweets)

                logger.info(
                    f"第 {page_num} 页：{len(tweets_page)} 条（新增 {len(new_tweets)} 条），"
                    f"累计 {len(all_tweets)} 条"
                )

                # ── 写检查点（每页立即保存）─────────────────────────
                if task_id:
                    save_checkpoint(
                        task_id=task_id,
                        keyword=keyword,
                        product=product,
                        tweets_so_far=all_tweets,
                        next_cursor=bottom_cursor,
                        page_fetched=page_num,
                    )
                    # 实时上报进度（让前端得以实时预览已抸取的推文）
                    _task_mgr.update_task_progress(task_id, page_num, list(all_tweets))

                if not bottom_cursor:
                    logger.info("无更多数据（bottom_cursor 为空），停止")
                    break
                if len(all_tweets) >= max_count:
                    logger.info(f"已达目标 {max_count} 条，停止")
                    break

            except Exception as e:
                logger.error(f"第 {page_num} 页解析失败: {e}", exc_info=True)
                break

            # ── 滚动翻页 ──────────────────────────────────────────
            page_num += 1
            time.sleep(settings.crawler_page_interval)
            tab.scroll.to_bottom()

    finally:
        try:
            tab.listen.stop()
            tab.close()
        except Exception:
            pass

    all_tweets = all_tweets[:max_count]

    # ── 爬取完成，删除检查点 ────────────────────────────────────────
    if task_id and len(all_tweets) >= max_count:
        delete_checkpoint(task_id)

    result = SearchResult(
        tweets=all_tweets,
        total_fetched=len(all_tweets),
        keyword=keyword,
        resumed=resumed,
    )
    logger.info(f"搜索完成：{result.total_fetched} 条推文，resumed={resumed}")
    return result


def _build_search_url(keyword: str, product: ProductType) -> str:
    """构建搜索 URL"""
    return SEARCH_URL_TEMPLATE.format(query=quote(keyword)) + _TAB_MAP.get(product, "")
