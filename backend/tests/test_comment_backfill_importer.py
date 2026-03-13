from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from api.services.comment_backfill_importer import analyze_comment_backfill_file


def test_analyze_comment_backfill_csv_filters_rows_and_dedups():
    content = (
        "平台,数据类型,推文ID,作者昵称,作者账号,作者ID,回复数,推文链接,推文内容\n"
        "x,原帖,1001,Alice,alice,1,5,https://x.com/alice/status/1001,hello\n"
        "x,评论,2001,Bob,bob,2,0,https://x.com/bob/status/2001,reply\n"
        "x,原帖,1002,Carol,carol,3,0,https://x.com/carol/status/1002,skip zero\n"
        "x,原帖,1001,Alice,alice,1,5,https://x.com/alice/status/1001,duplicate\n"
    ).encode("utf-8")

    result = analyze_comment_backfill_file("demo.csv", content, platform="x")

    assert result.summary["total_rows"] == 4
    assert result.summary["original_post_rows"] == 3
    assert result.summary["eligible_posts"] == 1
    assert result.summary["skipped_non_post_rows"] == 1
    assert result.summary["skipped_zero_comment_posts"] == 1
    assert result.summary["deduplicated_posts"] == 1
    assert result.tweets[0]["id"] == "1001"
    assert result.tweets[0]["author"]["screen_name"] == "alice"


def test_analyze_comment_backfill_xlsx_supports_weibo_without_platform_column():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["数据类型", "推文ID", "作者昵称", "作者ID", "回复数", "推文链接", "推文内容"])
    sheet.append(["原帖", "wb_1001", "微博作者", "8899", 9, "https://weibo.com/8899/wb_1001", "正文"])
    buf = BytesIO()
    workbook.save(buf)

    result = analyze_comment_backfill_file("demo.xlsx", buf.getvalue(), platform="weibo")

    assert result.summary["has_platform_column"] is False
    assert result.summary["eligible_posts"] == 1
    assert result.tweets[0]["platform"] == "weibo"
    assert result.tweets[0]["author"]["id"] == "8899"


def test_analyze_comment_backfill_rejects_platform_mismatch():
    content = (
        "平台,数据类型,推文ID,作者昵称,作者账号,作者ID,回复数,推文链接\n"
        "weibo,原帖,1001,Alice,alice,1,5,https://weibo.com/1/1001\n"
    ).encode("utf-8")

    with pytest.raises(HTTPException) as exc_info:
        analyze_comment_backfill_file("demo.csv", content, platform="x")

    assert exc_info.value.status_code == 400
    assert "平台为 weibo" in str(exc_info.value.detail)
