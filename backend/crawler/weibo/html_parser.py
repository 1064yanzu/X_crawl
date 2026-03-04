"""
微博搜索结果 HTML 解析器。
使用 BeautifulSoup4 解析 s.weibo.com 的搜索结果页面。
全面提取帖子信息：正文、作者、互动数据、来源、认证、话题、转发微博。
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from .models import WeiboPost

logger = logging.getLogger(__name__)


def _parse_count(text: str) -> int:
    """
    从文本中提取数字（如 '转发 3' → 3, '评论' → 0, '1.2万' → 12000）。
    """
    text = text.strip()
    m = re.search(r"([\d.]+)\s*万", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"([\d.]+)\s*亿", text)
    if m:
        return int(float(m.group(1)) * 100000000)
    m = re.search(r"(\d+)", text)
    if m:
        return int(m.group(1))
    return 0


def _extract_metrics_from_area(area: Tag) -> tuple[int, int, int]:
    """
    从一个互动区域（card-act 或 card-comment 内部）提取 转发/评论/赞 数。
    """
    reposts = 0
    comments = 0
    likes = 0

    lis = area.find_all("li")
    for li in lis:
        a_tag = li.find("a")
        if not a_tag:
            continue
        action_type = a_tag.get("action-type", "")
        suda = a_tag.get("suda-data", "")
        text = a_tag.get_text(strip=True)

        if action_type == "feed_list_forward" or "repost" in suda:
            reposts = _parse_count(text)
        elif action_type == "feed_list_comment" or "comment" in suda:
            comments = _parse_count(text)

    like_span = area.find("span", class_="woo-like-count")
    if like_span:
        likes = _parse_count(like_span.get_text(strip=True))

    return reposts, comments, likes


def _extract_hashtags(text_element: Tag) -> list[str]:
    """从正文 element 中提取所有话题标签。"""
    hashtags = []
    if text_element:
        for a in text_element.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if ("/weibo?q=%23" in href or "/weibo?q=#" in href) and text.startswith("#") and text.endswith("#"):
                hashtags.append(text.strip("#"))
    return hashtags


def _extract_source(from_div: Tag) -> str:
    """从 from 区域提取来源设备。"""
    if not from_div:
        return ""
    a_tags = from_div.find_all("a")
    if len(a_tags) >= 2:
        return a_tags[-1].get_text(strip=True)
    # 有时来源在纯文本中 "来自 xxx"
    full_text = from_div.get_text()
    m = re.search(r"来自\s*(.+?)$", full_text.strip())
    if m:
        return m.group(1).strip()
    return ""


def _extract_verified(card: Tag) -> tuple[bool, str]:
    """
    从帖子卡片提取用户认证信息。

    Returns:
        (verified, verified_type) — verified_type: 'blue'(企业/机构) / 'yellow'(个人) / ''
    """
    avator = card.find("div", class_="avator")
    if not avator:
        return False, ""

    if avator.find("svg", class_=re.compile(r"woo-icon--vblue")):
        return True, "blue"
    if avator.find(class_=re.compile(r"woo-icon--vblue")):
        return True, "blue"
    if avator.find("svg", class_=re.compile(r"woo-icon--vyellow")):
        return True, "yellow"
    if avator.find(class_=re.compile(r"woo-icon--vyellow")):
        return True, "yellow"
    # 也有可能 title 属性包含认证类型
    icon = avator.find("span", class_="woo-avatar-icon")
    if icon:
        title = icon.get("title", "")
        if "官方" in title or "企业" in title or "机构" in title:
            return True, "blue"
        if "个人" in title:
            return True, "yellow"
        if title:
            return True, "other"
    return False, ""


def _extract_repost_info(card: Tag) -> tuple[bool, str, str, int, int, int]:
    """
    从帖子卡片中提取转发微博信息。

    Returns:
        (is_repost, repost_text, repost_author, reposts, comments, likes)
    """
    comment_div = card.find("div", class_="card-comment")
    if not comment_div:
        return False, "", "", 0, 0, 0

    # 原始作者
    repost_author = ""
    name_a = comment_div.find("a", class_="name")
    if name_a:
        repost_author = name_a.get_text(strip=True).lstrip("@")

    # 原始正文
    repost_text = ""
    full_p = comment_div.find("p", attrs={"node-type": "feed_list_content_full"})
    if full_p:
        repost_text = full_p.get_text(separator=" ", strip=True)
    else:
        short_p = comment_div.find("p", attrs={"node-type": "feed_list_content"})
        if short_p:
            repost_text = short_p.get_text(separator=" ", strip=True)

    repost_text = re.sub(r"\s*(展开|收起)\s*$", "", repost_text).strip()

    # 原微博互动数据（在 card-comment 内部的 ul.act 中）
    reposts = 0
    comments = 0
    likes = 0
    act_ul = comment_div.find("ul", class_="act")
    if act_ul:
        reposts, comments, likes = _extract_metrics_from_area(act_ul)

    return True, repost_text, repost_author, reposts, comments, likes


def parse_search_page(html: str) -> tuple[list[WeiboPost], bool, int]:
    """
    解析搜索结果页 HTML。

    Returns:
        (posts, has_next, total_pages) — 帖子列表、是否有下一页、总页数（0=未知）。
    """
    soup = BeautifulSoup(html, "lxml")
    posts: list[WeiboPost] = []

    cards = soup.find_all("div", attrs={"action-type": "feed_list_item"})
    for card in cards:
        mid = card.get("mid", "")
        if not mid:
            continue

        # ---------- 用户信息 ----------
        name_tag = card.find("a", class_="name")
        author_name = name_tag.get("nick-name", "") if name_tag else ""
        if not author_name and name_tag:
            author_name = name_tag.get_text(strip=True)

        # 用户 ID（从链接提取）
        author_id = ""
        user_link = card.find("a", href=re.compile(r"//weibo\.com/\d+"))
        if user_link:
            m = re.search(r"//weibo\.com/(\d+)", user_link["href"])
            if m:
                author_id = m.group(1)

        # 头像
        avatar = ""
        avator_div = card.find("div", class_="avator")
        if avator_div:
            img = avator_div.find("img")
            if img and img.get("src", "").startswith("http"):
                avatar = img["src"]

        # 认证信息
        verified, verified_type = _extract_verified(card)

        # ---------- 时间、URL、来源 ----------
        created_at = ""
        post_url = ""
        source = ""
        # 主微博的 from（div.from），不在 card-comment 内部的
        content_div = card.find("div", class_="content", attrs={"node-type": "like"})
        from_div = None
        if content_div:
            from_div = content_div.find("div", class_="from", recursive=False)
            if not from_div:
                from_div = content_div.find("div", class_="from")
        if not from_div:
            from_div = card.find("div", class_="from")
        if not from_div:
            from_div = card.find("p", class_="from")

        if from_div:
            a_tags = from_div.find_all("a")
            if a_tags:
                created_at = a_tags[0].get_text(strip=True)
                href = a_tags[0].get("href", "")
                if href.startswith("//"):
                    post_url = "https:" + href
                elif href.startswith("http"):
                    post_url = href
            source = _extract_source(from_div)

        # ---------- 正文 ----------
        # 只取主微博的正文（不在 card-comment 内的）
        text_elem = None
        if content_div:
            full_p = content_div.find(
                "p", attrs={"node-type": "feed_list_content_full"}, recursive=False
            )
            if not full_p:
                # recursive=False 可能找不到，再试
                for p in content_div.find_all("p", attrs={"node-type": "feed_list_content_full"}):
                    # 确保不在 card-comment 内
                    if not p.find_parent("div", class_="card-comment"):
                        full_p = p
                        break
            if full_p:
                text_elem = full_p
            else:
                for p in content_div.find_all("p", attrs={"node-type": "feed_list_content"}):
                    if not p.find_parent("div", class_="card-comment"):
                        text_elem = p
                        break

        text = text_elem.get_text(separator=" ", strip=True) if text_elem else ""
        text = re.sub(r"\s*(展开|收起)\s*$", "", text).strip()

        # 话题标签
        hashtags = _extract_hashtags(text_elem)

        # ---------- 互动数据（主微博的 card-act） ----------
        reposts = 0
        comments_count = 0
        likes = 0
        card_act = card.find("div", class_="card-act")
        if card_act:
            reposts, comments_count, likes = _extract_metrics_from_area(card_act)

        # ---------- 转发微博信息 ----------
        is_repost, repost_text, repost_author, rp_reposts, rp_comments, rp_likes = (
            _extract_repost_info(card)
        )

        posts.append(
            WeiboPost(
                mid=mid,
                text=text,
                author_id=author_id,
                author_name=author_name,
                author_avatar=avatar,
                created_at=created_at,
                url=post_url,
                source=source,
                verified=verified,
                verified_type=verified_type,
                reposts_count=reposts,
                comments_count=comments_count,
                likes_count=likes,
                is_repost=is_repost,
                repost_text=repost_text,
                repost_author=repost_author,
                repost_reposts=rp_reposts,
                repost_comments=rp_comments,
                repost_likes=rp_likes,
                hashtags=hashtags,
            )
        )

    # 判断是否有下一页
    has_next = bool(
        soup.find("a", class_="next")
        or soup.find("a", string=re.compile(r"下一页"))
    )

    # 提取总页数（从分页器 ul.s-scroll 中的 li 数量）
    total_pages = 0
    page_list = soup.find("ul", class_="s-scroll")
    if page_list:
        page_items = page_list.find_all("li")
        total_pages = len(page_items)
    if total_pages == 0:
        # 备用：从 "第N页" 链接中提取最大页码
        for a in soup.find_all("a", string=re.compile(r"第\d+页")):
            m = re.search(r"第(\d+)页", a.get_text())
            if m:
                total_pages = max(total_pages, int(m.group(1)))

    return posts, has_next, total_pages
