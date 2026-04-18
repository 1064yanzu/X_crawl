from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummyTab:
    def __init__(self) -> None:
        self.url = ""
        self.html = "<html></html>"
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _DummyPost:
    def __init__(self, mid: str) -> None:
        self.mid = mid
        self.comments_count = 0
        self.author_id = f"author-{mid}"
        self.url = f"https://weibo.com/{mid}"

    def to_dict(self) -> dict:
        return {
            "id": self.mid,
            "mid": self.mid,
            "text": f"post-{self.mid}",
            "platform": "weibo",
            "replies": [],
        }


def test_weibo_resume_can_migrate_legacy_page_checkpoint_to_date_split(monkeypatch, tmp_path):
    from crawler.weibo import auth, checkpoints, date_splitter, html_parser, searcher
    from crawler import utils

    task_id = "resume-task"
    tab = _DummyTab()
    page_calls = {"count": 0}

    monkeypatch.setattr(checkpoints, "CHECKPOINTS_DIR", tmp_path)
    checkpoints.save_checkpoint(
        task_id,
        {
            "page": 51,
            "posts": [{"id": "legacy", "mid": "legacy", "text": "legacy", "platform": "weibo", "replies": []}],
            "keyword": "gemini",
            "start_date": "2023-01-01",
            "end_date": "2026-03-11",
        },
    )

    monkeypatch.setattr(searcher, "_get_tab_with_retry", lambda max_retries=2, browser_instance=None: tab)
    monkeypatch.setattr(auth, "ensure_weibo_login", lambda _tab: True)
    monkeypatch.setattr(auth, "ensure_search_cookies", lambda _tab: None)
    monkeypatch.setattr(date_splitter, "split_date_range", lambda *args, **kwargs: [("2023-01-01", "2023-01-31"), ("2023-02-01", "2023-02-28")])
    monkeypatch.setattr(utils, "check_signal", lambda task_id=None: None)
    monkeypatch.setattr(utils, "jittered_sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "interruptible_sleep", lambda *args, **kwargs: None)

    def fake_safe_get_html(_tab, url: str, wait_seconds: float = 3.0):
        page_calls["count"] += 1
        _tab.url = url
        _tab.html = "<html>ok</html>"
        return _tab.html, None

    def fake_parse_search_page(_html: str):
        mid = f"seg-{page_calls['count']}"
        return [_DummyPost(mid)], False, 1

    monkeypatch.setattr(searcher, "_safe_get_html", fake_safe_get_html)
    monkeypatch.setattr(html_parser, "parse_search_page", fake_parse_search_page)

    result = searcher.search(
        keyword="gemini",
        task_id=task_id,
        resume=True,
        fetch_comments=False,
        start_date="2023-01-01",
        end_date="2026-03-11",
    )

    assert result.resumed is True
    assert page_calls["count"] == 2
    assert [post["id"] for post in result.posts] == ["legacy", "seg-1", "seg-2"]

    checkpoint = checkpoints.load_checkpoint(task_id)
    assert checkpoint["mode"] == "date_split"
    assert checkpoint["next_segment_index"] == 2
    assert tab.closed is True


def test_run_weibo_task_forwards_resume_flag(monkeypatch):
    from api.services import crawl_service
    from crawler.weibo import searcher

    captured: dict = {}

    monkeypatch.setattr(crawl_service.task_manager, "update_task_phase", lambda *_args, **_kwargs: None)

    def fake_search(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(searcher, "search", fake_search)

    crawl_service._run_weibo_task(
        task_id="task-1",
        keyword="gemini",
        task_id_param="task-1",
        resume=False,
        start_date="2023-01-01",
        end_date="2026-03-11",
        fetch_replies=False,
    )

    assert captured["resume"] is False


def test_weibo_checkpoint_save_normalizes_weibo_comment_objects(monkeypatch, tmp_path):
    from crawler.weibo import checkpoints
    from crawler.weibo.models import WeiboComment

    task_id = "checkpoint-json-task"
    reply = WeiboComment(
        id="reply-1",
        text="checkpoint-reply",
        author_name="checkpoint-user",
        author_id="user-1",
        created_at="2026-03-10T03:00:00+00:00",
    )

    monkeypatch.setattr(checkpoints, "CHECKPOINTS_DIR", tmp_path)
    checkpoints.save_checkpoint(
        task_id,
        {
            "mode": "page",
            "page": 2,
            "keyword": "陈梦",
            "posts": [{"id": "mid-1", "replies": [reply]}],
            "start_date": "2024-08-01",
            "end_date": "2024-08-07",
        },
    )

    loaded = checkpoints.load_checkpoint(task_id)
    assert loaded["posts"][0]["replies"][0]["id"] == "reply-1"
